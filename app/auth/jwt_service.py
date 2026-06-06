from datetime import datetime, timedelta, timezone

import jwt

from app.models.jwt_claims import JWTClaims, Role


class JWTService:
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        expiration_minutes: int = 60,
    ) -> None:
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiration_minutes = expiration_minutes

    def create_token(
        self,
        subject: str,
        agent_id: str,
        role: Role,
    ) -> str:
        now = datetime.now(timezone.utc)

        claims = JWTClaims(
            sub=subject,
            agent_id=agent_id,
            role=role,
            iat=int(now.timestamp()),
            exp=int(
                (
                    now
                    + timedelta(
                        minutes=self.expiration_minutes
                    )
                ).timestamp()
            ),
        )

        return jwt.encode(
            claims.model_dump(mode="json"),
            self.secret_key,
            algorithm=self.algorithm,
        )

    def verify_token(self, token: str) -> JWTClaims:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                leeway=10,
            )

        except jwt.ExpiredSignatureError as e:
            raise ValueError("Token has expired") from e

        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}") from e

        return JWTClaims(**payload)