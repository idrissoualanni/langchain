# SHIM de compatibilité (refactor — phase migration).
#
# SubjectConfig/TopicConfig ont déménagé vers app/schemas/subject.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.schemas.subject import SubjectConfig, TopicConfig

__all__ = ["SubjectConfig", "TopicConfig"]
