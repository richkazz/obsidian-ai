from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import DATABASE_TYPE
from database import get_db
from models import Skill
from schemas import (
    SkillCreate,
    SkillUpdate,
    SkillResponse,
    SkillListResponse,
)
from auth import get_current_user, TokenData

if DATABASE_TYPE == "mongo":
    from database_mongo import get_database
    from models_mongo import SkillCollection

router = APIRouter(prefix="/skills", tags=["skills"])


def _to_response(skill, is_mongo=False) -> SkillResponse:
    if is_mongo:
        return SkillResponse(
            id=str(skill["_id"]),
            name=skill["name"],
            description=skill.get("description"),
            instructions=skill["instructions"],
            created_at=skill["created_at"],
            updated_at=skill.get("updated_at"),
        )
    return SkillResponse(
        id=str(skill.id),
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.get("", response_model=SkillListResponse)
async def list_skills(
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        skills = await SkillCollection.find_by_user(mongo_db, current_user.user_id)
        return SkillListResponse(skills=[_to_response(s, is_mongo=True) for s in skills])

    skills = db.query(Skill).filter(
        Skill.user_id == int(current_user.user_id),
        Skill.is_active == True,
    ).order_by(Skill.created_at.desc()).all()
    return SkillListResponse(skills=[_to_response(s) for s in skills])


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not body.instructions.strip():
        raise HTTPException(status_code=400, detail="Instructions are required")

    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        doc = {
            "user_id": current_user.user_id,
            "name": body.name.strip(),
            "description": body.description,
            "instructions": body.instructions,
        }
        created = await SkillCollection.create(mongo_db, doc)
        return _to_response(created, is_mongo=True)

    skill = Skill(
        user_id=int(current_user.user_id),
        name=body.name.strip(),
        description=body.description,
        instructions=body.instructions,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return _to_response(skill)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        skill = await SkillCollection.find_by_id(mongo_db, skill_id)
        if not skill or skill.get("user_id") != current_user.user_id or not skill.get("is_active", True):
            raise HTTPException(status_code=404, detail="Skill not found")
        return _to_response(skill, is_mongo=True)

    skill = db.query(Skill).filter(
        Skill.id == int(skill_id),
        Skill.user_id == int(current_user.user_id),
        Skill.is_active == True,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _to_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    body: SkillUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        existing = await SkillCollection.find_by_id(mongo_db, skill_id)
        if not existing or existing.get("user_id") != current_user.user_id:
            raise HTTPException(status_code=404, detail="Skill not found")
        updates = {}
        if body.name is not None:
            updates["name"] = body.name.strip()
        if body.description is not None:
            updates["description"] = body.description
        if body.instructions is not None:
            updates["instructions"] = body.instructions
        updated = await SkillCollection.update(mongo_db, skill_id, current_user.user_id, updates)
        return _to_response(updated, is_mongo=True)

    skill = db.query(Skill).filter(
        Skill.id == int(skill_id),
        Skill.user_id == int(current_user.user_id),
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if body.name is not None:
        skill.name = body.name.strip()
    if body.description is not None:
        skill.description = body.description
    if body.instructions is not None:
        skill.instructions = body.instructions

    db.commit()
    db.refresh(skill)
    return _to_response(skill)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if DATABASE_TYPE == "mongo":
        mongo_db = get_database()
        deleted = await SkillCollection.delete(mongo_db, skill_id, current_user.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"message": "Skill deleted"}

    skill = db.query(Skill).filter(
        Skill.id == int(skill_id),
        Skill.user_id == int(current_user.user_id),
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill.is_active = False
    db.commit()
    return {"message": "Skill deleted"}
