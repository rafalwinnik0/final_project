import os
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
from sqlalchemy.orm import Session
from starlette import status
from models import Project, User, Document
from schemas import CreateProject, UpdateProject, ListProject, CreateUser, UpdateDocument, ListDocument, ProjectWithDocs
from db import get_db, engine, Base
from auth import (oauth2_scheme, get_current_user, create_access_token, get_password_hash, verify_password,
                  verify_user_access_to_project, verify_owner_access_to_project)
from s3 import get_s3_client, ensure_unique_s3_key
from dotenv import load_dotenv
load_dotenv(".local.env")

app = FastAPI(title="Projects Service")
Base.metadata.create_all(bind=engine)

bucket_name = os.environ.get("BUCKET_NAME", "")

@app.post("/auth", status_code=status.HTTP_201_CREATED)
def create_user(schema: CreateUser, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == schema.username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if schema.password != schema.repeat_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords don't match")
    new_user = User(username=schema.username, password=get_password_hash(schema.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": f"{new_user.username} has been successfully created"}

@app.post("/login", status_code=status.HTTP_200_OK)
def login_into_service(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username==form_data.username).first()
    if user is None or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post('/projects', status_code=status.HTTP_201_CREATED)
def create_project(schema: CreateProject, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_project = Project(owner_id=user.id, **schema.dict())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return {"message": "The project successfully created."}

@app.get('/projects', status_code=status.HTTP_200_OK, response_model=List[ProjectWithDocs])
def get_all_users_projects(user: User = Depends(get_current_user)):
    projects = user.projects + user.participating_projects
    return projects

@app.get('/project/{project_id}/info', status_code=status.HTTP_200_OK, response_model=ProjectWithDocs)
def get_projects_details(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id==project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, project)
    return project

@app.put('/project/{id}', status_code=status.HTTP_200_OK)
def update_projects_details(
        schema: UpdateProject,
        id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, project)
    for key, value in schema.dict().items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return {"message": "The project's details successfully updated."}

@app.delete('/project/{id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
        id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        s3 = Depends(get_s3_client)
):
    project = db.query(Project).filter(Project.id==id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_owner_access_to_project(user, project)
    try:
        for document in project.documents:
            try:
                s3.delete_object(Bucket=bucket_name, Key=document.s3_key)
            except Exception as e:
                print(f"Warning: failed to delete {document.s3_key}: {str(e)}")
        db.delete(project)
        db.commit()
        return {"message": "Project successfully deleted."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Something went wrong while deleting: {str(e)}"
        )

@app.post("/project/{project_id}/invite", status_code=status.HTTP_200_OK)
def invite_user(
        project_id: int,
        user: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if current_user.username == user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot invite yourself")
    project = db.query(Project).filter(Project.id==project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_owner_access_to_project(current_user, project)
    participant = db.query(User).filter(User.username==user).first()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if participant in project.participants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already in project")
    project.participants.append(participant)
    db.commit()
    db.refresh(project)
    return {"message": f"{user} assigned to the project as a participant."}

####################### DOCUMENTS ########################

@app.get("/project/{project_id}/documents", status_code=status.HTTP_200_OK, response_model=List[ListDocument])
def return_all_projects_documents(
        project_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id==project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, project)
    return project.documents

@app.post("/project/{project_id}/documents", status_code=status.HTTP_201_CREATED)
def upload_document_for_project(
        project_id: int,
        file: UploadFile,
        user: User = Depends(get_current_user),
        s3 = Depends(get_s3_client),
        db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id==project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    verify_user_access_to_project(user, project)
    s3_key = f"{project_id}/{file.filename}"
    ensure_unique_s3_key(bucket_name, s3_key)
    try:
        s3.upload_fileobj(file.file, bucket_name, s3_key)
        document = Document(filename=file.filename, s3_key=s3_key, project_id=project_id)
        db.add(document)
        db.commit()
        db.refresh(document)
        return {"message": "The file successfully uploaded."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong while uploading."
        )

@app.get("/document/{document_id}", status_code=status.HTTP_200_OK)
def download_document(
        document_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        s3 = Depends(get_s3_client)
):
    document = db.query(Document).filter(Document.id==document_id).first()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, document.project)
    url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': document.s3_key},
        ExpiresIn=3600,
    )
    return {"url": url}

@app.put('/document/{document_id}', status_code=status.HTTP_200_OK)
def update_documents_details(
        document_id: int,
        file: UploadFile,
        user: User = Depends(get_current_user),
        s3 = Depends(get_s3_client),
        db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id==document_id).first()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    verify_user_access_to_project(user, document.project)
    s3_key = f"{document.project_id}/{file.filename}"
    try:
        if file.filename != document.filename:
            s3.delete_object(Bucket=bucket_name, Key=document.s3_key)
        s3.upload_fileobj(file.file, bucket_name, s3_key)
        document.filename = file.filename
        document.s3_key = s3_key
        db.commit()
        db.refresh(document)
        return {"message": "The details successfully updated."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.delete("/document/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
        document_id: int,
        user: User = Depends(get_current_user),
        s3 = Depends(get_s3_client),
        db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id==document_id).first()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_owner_access_to_project(user, document.project)
    try:
        s3.delete_object(Bucket=bucket_name, Key=document.s3_key)
        db.delete(document)
        db.commit()
        return {"message": "Document deleted."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)