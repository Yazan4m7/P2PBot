from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .database import Database
from .domain import SimulationStatus, SimulatorError
from .models import SimulationRow


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class VirtualClock:
    def __init__(self, db: Database, simulation_id: str):
        self.db = db
        self.simulation_id = simulation_id

    def _row(self, session):
        row = session.get(SimulationRow, self.simulation_id)
        if row is None:
            raise SimulatorError("SIMULATION_NOT_FOUND", self.simulation_id, status_code=404)
        return row

    def now(self) -> datetime:
        with self.db.session() as session:
            row = self._row(session)
            if row.status == SimulationStatus.PAUSED.value or row.speed == 0:
                return aware(row.base_simulated_at)
            delta = utcnow() - aware(row.base_real_at)
            return aware(row.base_simulated_at) + timedelta(seconds=delta.total_seconds() * row.speed)

    def pause(self) -> datetime:
        with self.db.session() as session:
            row = self._row(session)
            if row.status == SimulationStatus.PAUSED.value:
                return aware(row.base_simulated_at)
            current = aware(row.base_simulated_at) + timedelta(seconds=(utcnow() - aware(row.base_real_at)).total_seconds() * row.speed)
            row.base_simulated_at = current
            row.base_real_at = utcnow()
            row.status = SimulationStatus.PAUSED.value
            session.commit()
            return current

    def resume(self) -> datetime:
        with self.db.session() as session:
            row = self._row(session)
            row.base_real_at = utcnow()
            row.status = SimulationStatus.ACTIVE.value
            session.commit()
            return aware(row.base_simulated_at)

    def set_speed(self, speed: float) -> float:
        if speed < 0 or speed > 1000:
            raise SimulatorError("INVALID_SPEED", "speed must be 0..1000")
        with self.db.session() as session:
            row = self._row(session)
            current = aware(row.base_simulated_at)
            if row.status != SimulationStatus.PAUSED.value and row.speed != 0:
                current = current + timedelta(seconds=(utcnow() - aware(row.base_real_at)).total_seconds() * row.speed)
            row.base_simulated_at = current
            row.base_real_at = utcnow()
            row.speed = speed
            if speed == 0:
                row.status = SimulationStatus.PAUSED.value
            session.commit()
            return speed

    def advance(self, seconds: float) -> datetime:
        if seconds < 0:
            raise SimulatorError("INVALID_ADVANCE", "cannot move virtual time backwards")
        with self.db.session() as session:
            row = self._row(session)
            current = aware(row.base_simulated_at)
            if row.status != SimulationStatus.PAUSED.value and row.speed != 0:
                current = current + timedelta(seconds=(utcnow() - aware(row.base_real_at)).total_seconds() * row.speed)
            row.base_simulated_at = current + timedelta(seconds=seconds)
            row.base_real_at = utcnow()
            session.commit()
            return aware(row.base_simulated_at)
