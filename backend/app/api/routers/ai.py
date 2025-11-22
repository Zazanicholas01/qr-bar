from fastapi import APIRouter, HTTPException, Query

from app.ai.search import search_menu
from app.ai.search import _ITEM_DOCS  # reuse in-memory docs to surface tags/metadata


router = APIRouter()


@router.get("/search")
def search(q: str = Query(..., min_length=2, description="Search query"), limit: int = Query(5, ge=1, le=20)):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    results = search_menu(q, limit=limit)
    return {"query": q, "results": results}


@router.get("/tags")
def tags():
    """Return item metadata (tags, allergens, ingredients, description) by id.

    This helps the frontend filter full menu items without embedding NLP client-side.
    """
    items = [
        {
            "id": doc.id,
            "name": doc.name,
            "description": doc.description,
            "ingredients": doc.ingredients,
            "allergens": doc.allergens,
            "tags": doc.tags,
        }
        for doc in _ITEM_DOCS
    ]
    return {"items": items}
