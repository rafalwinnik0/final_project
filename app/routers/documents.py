from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import Document, Project, User
from app.schemas import ListDocument
from app.services import (get_current_user, verify_user_access_to_project, verify_owner_access_to_project,
                               get_s3_client, ensure_unique_s3_key)
bucket_name = "bucket-ag1929"
router = APIRouter(prefix="/projects/{project_id}/documents", tags=["Documents"])

@router.get("", status_code=status.HTTP_200_OK, response_model=List[ListDocument])
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

@router.post("", status_code=status.HTTP_201_CREATED)
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

@router.get("/{document_id}", status_code=status.HTTP_200_OK)
def download_document(
        project_id: int,
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

@router.put('/{document_id}', status_code=status.HTTP_200_OK)
def update_documents_details(
        project_id: int,
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

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
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