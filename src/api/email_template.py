from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from src.db import get_db
from src.auth import get_current_user
from src.models.email_template import EmailTemplate

router = APIRouter()

class EmailTemplateBase(BaseModel):
    template_type: str
    subject: str
    body: str

class EmailTemplateResponse(EmailTemplateBase):
    id: str

    class Config:
        from_attributes = True

@router.get("/email-template", response_model=List[EmailTemplateResponse])
def get_email_templates(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    templates = db.query(EmailTemplate).filter(EmailTemplate.user_id == current_user.id).all()
    return templates

@router.put("/email-template", response_model=EmailTemplateResponse)
def save_email_template(data: EmailTemplateBase, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    template = db.query(EmailTemplate).filter(
        EmailTemplate.user_id == current_user.id,
        EmailTemplate.template_type == data.template_type
    ).first()
    
    if template:
        template.subject = data.subject
        template.body = data.body
    else:
        template = EmailTemplate(
            user_id=current_user.id,
            template_type=data.template_type,
            subject=data.subject,
            body=data.body
        )
        db.add(template)
        
    db.commit()
    db.refresh(template)
    return template
