import os
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
from sqlalchemy.orm import Session
from starlette import status
from app.models import Project, User, Document
from app.schemas import CreateProject, UpdateProject, ListProject, CreateUser, UpdateDocument, ListDocument, ProjectWithDocs
from app.db import get_db, engine, Base
from app.services import (oauth2_scheme, get_current_user, create_access_token, get_password_hash, verify_password,
                               verify_user_access_to_project, verify_owner_access_to_project)
from app.services import get_s3_client, ensure_unique_s3_key
from app.routers import projects, documents

app = FastAPI(title="Projects Service")
Base.metadata.create_all(bind=engine)

bucket_name = "bucket-ag1929"

app.include_router(projects.router)
app.include_router(documents.router)

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


