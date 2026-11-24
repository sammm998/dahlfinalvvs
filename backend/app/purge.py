"""Det som tas bort med en ritning och med ett projekt.

Databasen håller sina främmande nycklar (`PRAGMA foreign_keys=ON`), och det är rätt: en markering får inte peka på
en ritning som inte finns. Men då måste allt som hör till ritningen gå först. Innan det här fanns kunde en ritning
med en enda egen markering inte tas bort alls - svaret blev ett serverfel - och samma sak för en ritning med
rättelser, en kalibrering, en kontrollerad mängd eller lästa rum.

Det som tas bort är det som bara gäller ritningen: markeringar, kalibreringar, utsnitt, rättelser, agentens recept,
kontrollerade mängder, kalkyler, dokumentbeslut, lästa rum och krav. Ett CAD-blad är projektets och står kvar; det
släpper bara sin koppling till ritningen. Lärda regler bär bara receptets id som text och står kvar - de har sin
egen prövning och sitt eget liv.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .db import (AgentRecipe, AnalysisJob, CadRevision, CadSheet, Calculation, Calibration, ConfirmedTakeoff,
                 Correction, DisciplineOverride, DocumentOverride, Drawing, DrawingViewport, Markup, Project,
                 ProjectAnalysis, ProjectEstimate, Requirement, Space)


def purge_drawing(db: Session, d: Drawing) -> None:
    """Everything that belongs to the drawing alone, so the drawing itself can go."""
    jobs = [j.id for j in db.query(AnalysisJob.id).filter(AnalysisJob.drawing_id == d.id).all()]
    q = lambda model: db.query(model)  # noqa: E731
    q(Markup).filter(Markup.drawing_id == d.id).delete(synchronize_session=False)
    q(Calibration).filter(Calibration.drawing_id == d.id).delete(synchronize_session=False)
    q(DrawingViewport).filter(DrawingViewport.drawing_id == d.id).delete(synchronize_session=False)
    q(Space).filter(Space.drawing_id == d.id).delete(synchronize_session=False)
    q(Requirement).filter(Requirement.drawing_id == d.id).delete(synchronize_session=False)
    q(DocumentOverride).filter(DocumentOverride.drawing_id == d.id).delete(synchronize_session=False)
    q(Correction).filter(Correction.drawing_id == d.id).delete(synchronize_session=False)
    q(AgentRecipe).filter(AgentRecipe.drawing_id == d.id).delete(synchronize_session=False)
    q(ConfirmedTakeoff).filter(ConfirmedTakeoff.drawing_id == d.id).delete(synchronize_session=False)
    if jobs:
        q(Correction).filter(Correction.job_id.in_(jobs)).delete(synchronize_session=False)
        q(AgentRecipe).filter(AgentRecipe.job_id.in_(jobs)).delete(synchronize_session=False)
        q(ConfirmedTakeoff).filter(ConfirmedTakeoff.job_id.in_(jobs)).delete(synchronize_session=False)
        q(Calculation).filter(Calculation.job_id.in_(jobs)).delete(synchronize_session=False)
    for sheet in q(CadSheet).filter(CadSheet.drawing_id == d.id).all():
        sheet.drawing_id = None
    db.flush()


def purge_project(db: Session, p: Project) -> None:
    """Every drawing's own rows, and then what belongs to the project."""
    for d in list(p.drawings):
        purge_drawing(db, d)
    q = lambda model: db.query(model)  # noqa: E731
    sheets = [s.id for s in q(CadSheet.id).filter(CadSheet.project_id == p.id).all()]
    if sheets:
        q(CadRevision).filter(CadRevision.sheet_id.in_(sheets)).delete(synchronize_session=False)
        q(CadSheet).filter(CadSheet.id.in_(sheets)).delete(synchronize_session=False)
    q(Space).filter(Space.project_id == p.id).delete(synchronize_session=False)
    q(Requirement).filter(Requirement.project_id == p.id).delete(synchronize_session=False)
    q(ProjectEstimate).filter(ProjectEstimate.project_id == p.id).delete(synchronize_session=False)
    q(DocumentOverride).filter(DocumentOverride.project_id == p.id).delete(synchronize_session=False)
    q(ProjectAnalysis).filter(ProjectAnalysis.project_id == p.id).delete(synchronize_session=False)
    q(DisciplineOverride).filter(DisciplineOverride.project_id == p.id).delete(synchronize_session=False)
    from .db import TechSpec
    q(TechSpec).filter(TechSpec.project_id == p.id).delete(synchronize_session=False)
    from .storage import storage
    storage.delete_prefix(f"techspecs/{p.id}")
    # Allt annat som pekar på projektet (SmartHangers-uppsättningar, offerter, och det som läggs till senare):
    # en rad som måste ha projektet tas bort, en som kan stå utan släpper det. Utan detta faller borttagningen
    # på databasens främmande nyckel så fort projektet har något som inte står uppräknat ovan.
    from sqlalchemy import delete as _delete, update as _update
    from .db import Base, HangerSet
    for hs in q(HangerSet).filter(HangerSet.project_id == p.id).all():
        storage.delete_prefix(f"prefab/{hs.id}")
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "drawings":
            continue                                   # ritningarna och deras analyser: purge_drawing ovan
        for col in table.columns:
            if any(fk.column.table.name == "projects" and fk.column.name == "id" for fk in col.foreign_keys):
                if col.nullable:
                    db.execute(_update(table).where(col == p.id).values({col.name: None}))
                else:
                    db.execute(_delete(table).where(col == p.id))
    db.flush()
