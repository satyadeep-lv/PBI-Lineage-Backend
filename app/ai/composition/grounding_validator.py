from app.ai.models.evidence import EvidenceBundle, GroundedClaim


class GroundingRejectedError(Exception):
    """A model-produced claim failed mechanical grounding checks.

    Fails closed: any one bad claim rejects the entire response rather than
    stripping the offending citation and keeping the sentence.
    """


class GroundedResponseValidator:
    @staticmethod
    def validate(
        claims: list[GroundedClaim],
        bundle: EvidenceBundle,
    ) -> list[GroundedClaim]:
        if not claims:
            raise GroundingRejectedError("The model produced no claims.")

        valid_evidence_ids = {item.evidence_id for item in bundle.evidence}

        for claim in claims:
            if not claim.evidence_ids:
                raise GroundingRejectedError(
                    f"Claim has no evidence_ids: {claim.text!r}"
                )

            for evidence_id in claim.evidence_ids:
                if evidence_id not in valid_evidence_ids:
                    raise GroundingRejectedError(
                        f"Claim cites unknown evidence_id "
                        f"{evidence_id!r}: {claim.text!r}"
                    )

        return claims
