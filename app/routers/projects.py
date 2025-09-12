from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import Project, User
from app.schemas import CreateProject, UpdateProject, ProjectWithDocs
from app.services import (get_current_user, verify_user_access_to_project, verify_owner_access_to_project, get_s3_client,
                          ensure_unique_s3_key)

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post('', status_code=status.HTTP_201_CREATED)
def create_project(schema: CreateProject, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_project = Project(owner_id=user.id, **schema.dict())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    print(new_project.id)
    return {"message": "The project successfully created."}

@router.get('', status_code=status.HTTP_200_OK, response_model=List[ProjectWithDocs])
def get_all_users_projects(user: User = Depends(get_current_user)):
    projects = user.projects + user.participating_projects
    return projects

@router.get('/{project_id}', status_code=status.HTTP_200_OK, response_model=ProjectWithDocs)
def get_projects_details(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id==project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, project)
    return project

@router.put('/{project_id}', status_code=status.HTTP_200_OK)
def update_projects_details(
        schema: UpdateProject,
        project_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    verify_user_access_to_project(user, project)
    for key, value in schema.dict().items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return {"message": "The project's details successfully updated."}

@router.delete('/{project_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
        project_id: int,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
        s3 = Depends(get_s3_client)
):
    project = db.query(Project).filter(Project.id==project_id).first()
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

@router.post("/{project_id}/invite", status_code=status.HTTP_200_OK)
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