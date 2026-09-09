# class MicrosoftAuthService:

#     def prepare_powerbi_auth(
#         self,
#         *,
#         tenant_id: str,
#         client_id: str,
#     ) -> MicrosoftAuthPreparationResponse:
#         authority = (
#             f"{MICROSOFT_LOGIN_BASE_URL}/"
#             f"{tenant_id}"
#         )

#         return MicrosoftAuthPreparationResponse(
#             provider="powerbi",
#             tenant_id=tenant_id,
#             client_id=client_id,
#             authority=authority,
#             scopes=POWERBI_SCOPES,
#         )

#     def prepare_fabric_auth(
#         self,
#         *,
#         tenant_id: str,
#         client_id: str,
#     ) -> MicrosoftAuthPreparationResponse:
#         authority = (
#             f"{MICROSOFT_LOGIN_BASE_URL}/"
#             f"{tenant_id}"
#         )

#         return MicrosoftAuthPreparationResponse(
#             provider="fabric",
#             tenant_id=tenant_id,
#             client_id=client_id,
#             authority=authority,
#             scopes=FABRIC_SCOPES,
#         )
