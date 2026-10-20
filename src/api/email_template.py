from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from src.db import get_db
from src.auth import get_current_user
from src.models.email_template import EmailTemplate
from src.services.plan_features import plan_has_feature

router = APIRouter()

# Email templates are keyed by invoice status; SMS templates by "sms_" +
# status. They used to share the same keys, so saving an SMS template
# silently overwrote the email template for that stage (and vice versa).
EMAIL_TEMPLATE_TYPES = {"upcoming", "due", "overdue"}
SMS_TEMPLATE_TYPES = {"sms_upcoming", "sms_due", "sms_overdue"}
VALID_TEMPLATE_TYPES = EMAIL_TEMPLATE_TYPES | SMS_TEMPLATE_TYPES
SMS_MAX_LENGTH = 320


class EmailTemplateBase(BaseModel):
    template_type: str
    subject: str
    body: str


class EmailTemplateResponse(EmailTemplateBase):
    id: str

    class Config:
        from_attributes = True


@router.get("/email-template", response_model=List[EmailTemplateResponse])
def get_email_templates(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    templates = db.query(EmailTemplate).filter(EmailTemplate.user_id == current_user.id).all()
    return templates


@router.put("/email-template", response_model=EmailTemplateResponse)
def save_email_template(data: EmailTemplateBase, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not plan_has_feature(current_user.subscription_plan, "custom_templates"):
        raise HTTPException(
            status_code=403,
            detail="Custom reminder templates are available on the Growth plan and above. Upgrade to customize your reminders.",
        )
    if data.template_type not in VALID_TEMPLATE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown template type: {data.template_type}")
    if not data.body.strip():
        raise HTTPException(status_code=422, detail="Template body cannot be empty")
    if data.template_type in SMS_TEMPLATE_TYPES and len(data.body) > SMS_MAX_LENGTH:
        raise HTTPException(status_code=422, detail=f"SMS templates are limited to {SMS_MAX_LENGTH} characters")
    if data.template_type in EMAIL_TEMPLATE_TYPES and not data.subject.strip():
        raise HTTPException(status_code=422, detail="Email templates need a subject")
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
