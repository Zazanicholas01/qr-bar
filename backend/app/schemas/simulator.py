from pydantic import BaseModel


class SimulationStartResponse(BaseModel):
    message: str
    total_users: int
