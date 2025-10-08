from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.routers import menu as menu_router


def _normalize(text: str) -> str:
    # Lowercase, strip accents, keep letters/numbers/spaces
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9àèéìòóù\s]", " ", text)  # keep basic chars + spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> List[str]:
    text = _normalize(text)
    return [t for t in text.split(" ") if t]


# Minimal Italian/English synonym and expansion map to improve recall
SYNONYMS: Dict[str, List[str]] = {
    "rinfrescante": ["fresco", "dissetante", "rinfresco"],
    "citrusy": ["agrumato", "arancia", "limone", "citrico"],
    "citrico": ["agrumato", "arancia", "limone"],
    "frizzante": ["gassata", "bollicine", "sparkling"],
    "dolce": ["zuccherato", "morbido", "sweet"],
    "amaro": ["bitter"],
    "spritz": ["aperol", "prosecco"],
    "birra": ["beer"],
    "vino": ["wine"],
    "menta": ["mint"],
    "lime": ["limone"],
    "arancia": ["orange"],
    "pesca": ["peach"],
    "caffe": ["espresso", "caffeina"],
    "latte": ["milk", "latticini"],
    "analcolico": ["senza alcol", "senza alcool", "no alcohol", "senza-alcol"],
    "alcolico": ["con alcol", "alcool"],
    "senza zucchero": ["senza-zucchero", "no sugar"],
    "gluten": ["glutine"],
    "senza glutine": ["gluten free", "senza-glutine"],
    "vegano": ["vegan"],
    "vegetariano": ["vegetarian"],
    "caffeina": ["caffe", "caffein", "caffeine"],
}


# Descriptions to enrich the menu semantics (kept in backend so search is server-driven)
DESCRIPTIONS: Dict[str, str] = {
    "Espresso": "Estratto in 25 secondi con miscela arabica 70%, corpo pieno e note tostate.",
    "Espresso Macchiato": "Espresso con un tocco di latte montato, finale vellutato e bilanciato.",
    "Cappuccino": "Espresso e latte montato setoso, con spolverata di cacao amaro, cremoso e avvolgente.",
    "Latte Macchiato": "Strati di latte caldo e caffe, gusto delicato e rotondo, perfetto per chi ama la morbidezza.",
    "Caffè Americano": "Espresso allungato con acqua calda, profilo piu lungo e delicato, bassa intensita.",
    "Succo d'arancia": "Spremuta fresca di arance, agrumata e rinfrescante, ricca di vitamina C.",
    "Acqua naturale": "Acqua naturale bilanciata, servita fresca. Scelta leggera e sempre adatta.",
    "Acqua frizzante": "Acqua gassata leggera e frizzante, con bollicine vivaci, dissetante.",
    "Tè freddo": "Infuso freddo alla pesca, leggermente dolce e dissetante, servito con ghiaccio.",
    "Vino bianco": "Selezione del giorno: profumi floreali, agrumi e finale minerale, ottimo aperitivo.",
    "Vino rosso": "Rosso di corpo medio con note di frutti di bosco e leggere spezie, tannino morbido.",
    "Birra artigianale": "Birra dal gusto deciso con profumo di luppolo, amaro equilibrato e finale secco.",
    "Spritz": "Classico veneziano con prosecco, Aperol e soda: agrumato, leggermente amaro e frizzante.",
    "Negroni": "Gin, vermouth rosso e bitter: intenso, deciso e piacevolmente amaro.",
    "Mojito": "Rum bianco, lime e menta fresca: rinfrescante, agrumato e vivace, con un tocco di soda.",
    "Espresso Martini": "Vodka, espresso e liquore al caffe: vellutato, energizzante e leggermente dolce.",
}

# Item metadata for ingredients/allergens/tags
ITEM_METADATA: Dict[str, Dict[str, List[str] | str]] = {
    "Espresso": {
        "ingredients": ["acqua", "caffe"],
        "allergens": ["caffeina"],
        "tags": ["caldo", "caffeina", "amaro", "senza-zucchero", "senza-glutine", "analcolico", "vegano", "vegetariano"],
    },
    "Espresso Macchiato": {
        "ingredients": ["espresso", "latte"],
        "allergens": ["latte", "lattosio"],
        "tags": ["caldo", "caffeina", "latte", "cremoso", "vegetariano"],
    },
    "Cappuccino": {
        "ingredients": ["espresso", "latte", "cacao"],
        "allergens": ["latte", "lattosio"],
        "tags": ["caldo", "caffeina", "latte", "dolce", "cremoso", "vegetariano"],
    },
    "Latte Macchiato": {
        "ingredients": ["latte", "espresso"],
        "allergens": ["latte", "lattosio"],
        "tags": ["caldo", "latte", "delicato", "vegetariano"],
    },
    "Caffè Americano": {
        "ingredients": ["espresso", "acqua"],
        "allergens": ["caffeina"],
        "tags": ["caldo", "caffeina", "delicato", "senza-zucchero", "senza-glutine", "analcolico", "vegano", "vegetariano"],
    },
    "Succo d'arancia": {
        "ingredients": ["arancia"],
        "allergens": [],
        "tags": ["agrumato", "freddo", "analcolico", "rinfrescante", "senza-glutine", "vegano", "vegetariano"],
    },
    "Acqua naturale": {
        "ingredients": ["acqua"],
        "allergens": [],
        "tags": ["analcolico", "senza-zucchero", "senza-glutine", "freddo", "neutra", "vegano", "vegetariano"],
    },
    "Acqua frizzante": {
        "ingredients": ["acqua", "anidride carbonica"],
        "allergens": [],
        "tags": ["frizzante", "analcolico", "freddo", "rinfrescante", "senza-glutine", "vegano", "vegetariano"],
    },
    "Tè freddo": {
        "ingredients": ["tè", "acqua", "pesca", "zucchero"],
        "allergens": [],
        "tags": ["freddo", "dolce", "analcolico", "pesca", "rinfrescante", "vegetariano"],
    },
    "Vino bianco": {
        "ingredients": ["uva"],
        "allergens": ["solfiti"],
        "tags": ["alcolico", "fresco", "fruttato", "aperitivo"],
    },
    "Vino rosso": {
        "ingredients": ["uva"],
        "allergens": ["solfiti"],
        "tags": ["alcolico", "corposo", "tannico"],
    },
    "Birra artigianale": {
        "ingredients": ["acqua", "malto d'orzo", "luppolo", "lievito"],
        "allergens": ["glutine"],
        "tags": ["alcolico", "frizzante", "amaro", "luppolato"],
    },
    "Spritz": {
        "ingredients": ["prosecco", "aperol", "soda", "arancia"],
        "allergens": ["solfiti"],
        "tags": ["alcolico", "aperitivo", "agrumato", "frizzante", "leggermente amaro"],
    },
    "Negroni": {
        "ingredients": ["gin", "vermouth rosso", "bitter"],
        "allergens": ["solfiti"],
        "tags": ["alcolico", "amaro", "forte", "classico"],
    },
    "Mojito": {
        "ingredients": ["rum bianco", "lime", "menta", "zucchero", "soda"],
        "allergens": [],
        "tags": ["alcolico", "agrumato", "menta", "rinfrescante", "freddo", "frizzante"],
    },
    "Espresso Martini": {
        "ingredients": ["vodka", "espresso", "liquore al caffe", "zucchero"],
        "allergens": ["caffeina"],
        "tags": ["alcolico", "caffeina", "dolce", "freddo"],
    },
}


@dataclass
class ItemDoc:
    id: int
    name: str
    price: float
    text: str  # name + description + categories + ingredients + allergens + tags
    description: str
    ingredients: List[str]
    allergens: List[str]
    tags: List[str]


class TfidfIndex:
    def __init__(self, docs: List[ItemDoc]):
        self.docs = docs
        self.vocab: Dict[str, int] = {}
        self.idf: List[float] = []
        self.vectors: List[Dict[int, float]] = []  # sparse tf-idf per doc
        self._build()

    def _build(self) -> None:
        tokenized_docs = [
            _tokenize(doc.text) for doc in self.docs
        ]

        # Build DF
        df: Dict[str, int] = {}
        for tokens in tokenized_docs:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        # Vocab ordering
        self.vocab = {term: i for i, term in enumerate(sorted(df.keys()))}
        n_docs = len(self.docs)
        # Smooth IDF
        self.idf = [math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1.0 for term in sorted(df.keys())]

        # Build TF-IDF vectors (sparse dict: idx -> weight)
        self.vectors = []
        for tokens in tokenized_docs:
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            total = float(len(tokens)) or 1.0
            vec: Dict[int, float] = {}
            norm = 0.0
            for term, count in tf.items():
                idx = self.vocab.get(term)
                if idx is None:
                    continue
                weight = (count / total) * self.idf[idx]
                vec[idx] = weight
                norm += weight * weight
            norm = math.sqrt(norm) or 1.0
            # normalize
            for idx in list(vec.keys()):
                vec[idx] /= norm
            self.vectors.append(vec)

    def _expand_query_tokens(self, tokens: List[str]) -> List[str]:
        expanded = list(tokens)
        for t in tokens:
            for alt in SYNONYMS.get(t, []):
                expanded.append(alt)
        return expanded

    def query(self, text: str, top_k: int = 5) -> List[Tuple[int, float]]:
        tokens = self._expand_query_tokens(_tokenize(text))
        if not tokens:
            return []
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = float(len(tokens))
        qvec: Dict[int, float] = {}
        norm = 0.0
        for term, count in tf.items():
            idx = self.vocab.get(term)
            if idx is None:
                continue
            weight = (count / total) * self.idf[idx]
            qvec[idx] = weight
            norm += weight * weight
        norm = math.sqrt(norm) or 1.0
        for idx in list(qvec.keys()):
            qvec[idx] /= norm

        # Cosine similarity for sparse vectors
        scores: List[Tuple[int, float]] = []
        if not qvec:
            return scores
        for i, dvec in enumerate(self.vectors):
            score = 0.0
            # iterate over smaller dict
            if len(qvec) <= len(dvec):
                for idx, w in qvec.items():
                    if idx in dvec:
                        score += w * dvec[idx]
            else:
                for idx, w in dvec.items():
                    if idx in qvec:
                        score += w * qvec[idx]
            scores.append((i, float(score)))

        scores.sort(key=lambda x: x[1], reverse=True)
        if top_k:
            scores = scores[:top_k]
        return scores


def _collect_item_docs() -> List[ItemDoc]:
    docs: List[ItemDoc] = []
    for category in menu_router.CATEGORIES:
        cat_name = category.get("name", "")
        for item in category.get("items", []):
            name = item.get("name", "")
            desc = DESCRIPTIONS.get(name, "")
            meta = ITEM_METADATA.get(name, {"ingredients": [], "allergens": [], "tags": []})
            ingredients = [str(x) for x in meta.get("ingredients", [])]
            allergens = [str(x) for x in meta.get("allergens", [])]
            tags = [str(x) for x in meta.get("tags", [])]
            # Text = name + description + category + ingredients/allergens/tags
            parts = [name, desc, cat_name]
            if ingredients:
                parts.append("ingredienti: " + ", ".join(ingredients))
            if allergens:
                parts.append("allergeni: " + ", ".join(allergens))
            if tags:
                parts.append("tags: " + ", ".join(tags))
            text = ". ".join([p for p in parts if p])
            docs.append(
                ItemDoc(
                    id=int(item["id"]),
                    name=name,
                    price=float(item.get("price", 0.0)),
                    text=text,
                    description=desc,
                    ingredients=ingredients,
                    allergens=allergens,
                    tags=tags,
                )
            )
    return docs


# Global in-memory index built at import time
_ITEM_DOCS = _collect_item_docs()
INDEX = TfidfIndex(_ITEM_DOCS)


def search_menu(query: str, limit: int = 5) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    matches = INDEX.query(query, top_k=limit)
    for doc_idx, score in matches:
        doc = _ITEM_DOCS[doc_idx]
        results.append(
            {
                "id": doc.id,
                "name": doc.name,
                "price": doc.price,
                "score": round(float(score), 4),
                "description": doc.description,
                "ingredients": doc.ingredients,
                "allergens": doc.allergens,
                "tags": doc.tags,
            }
        )
    return results
