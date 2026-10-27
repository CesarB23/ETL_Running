"""Reglas puras de alerta: reciben datos ya calculados y no consultan el lake."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Severity = Literal["info", "warning", "critical"]

ACWR_THRESHOLD = 1.5
INACTIVITY_DAYS = 10
COMPLIANCE_THRESHOLD = 50.0
FRESHNESS_HOURS = 36.0
API_KEY_WARNING_DAYS = 14


@dataclass(frozen=True)
class Alert:
    code: str
    severity: Severity
    message: str
    value: float | None = None

    def as_log_line(self, now: datetime) -> str:
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"{stamp} | {self.severity.upper()} | {self.code} | {self.message}"


@dataclass(frozen=True)
class AlertContext:
    acwr: float | None = None
    acwr_reliable: bool = False
    days_since_last_run: int | None = None
    plan_compliance_pct: float | None = None
    data_age_hours: float | None = None
    api_key_days_left: int | None = None


def acwr_alert(context: AlertContext) -> list[Alert]:
    if not context.acwr_reliable or context.acwr is None:
        return []
    if context.acwr <= ACWR_THRESHOLD:
        return []
    return [
        Alert(
            code="acwr_high",
            severity="warning",
            message=(
                f"ACWR {context.acwr:.2f} supera {ACWR_THRESHOLD}; "
                "revisa el aumento de carga antes de la siguiente sesión."
            ),
            value=context.acwr,
        )
    ]


def inactivity_alert(context: AlertContext) -> list[Alert]:
    if context.days_since_last_run is None or context.days_since_last_run <= INACTIVITY_DAYS:
        return []
    return [
        Alert(
            code="inactivity",
            severity="warning",
            message=(
                f"Última carrera hace {context.days_since_last_run} días "
                f"(umbral: {INACTIVITY_DAYS})."
            ),
            value=float(context.days_since_last_run),
        )
    ]


def compliance_alert(context: AlertContext) -> list[Alert]:
    if context.plan_compliance_pct is None:
        return []
    if context.plan_compliance_pct >= COMPLIANCE_THRESHOLD:
        return []
    return [
        Alert(
            code="plan_compliance_low",
            severity="warning",
            message=(
                f"Cumplimiento del plan {context.plan_compliance_pct:.1f}% "
                f"por debajo de {COMPLIANCE_THRESHOLD:.0f}% en la última semana cerrada."
            ),
            value=context.plan_compliance_pct,
        )
    ]


def freshness_alert(context: AlertContext) -> list[Alert]:
    if context.data_age_hours is None or context.data_age_hours <= FRESHNESS_HOURS:
        return []
    return [
        Alert(
            code="data_stale",
            severity="warning",
            message=(
                f"El warehouse no se actualiza desde hace {context.data_age_hours:.1f} h "
                f"(umbral: {FRESHNESS_HOURS:.0f} h)."
            ),
            value=context.data_age_hours,
        )
    ]


def api_key_expiry_alert(context: AlertContext) -> list[Alert]:
    if context.api_key_days_left is None or context.api_key_days_left > API_KEY_WARNING_DAYS:
        return []
    if context.api_key_days_left < 0:
        return [
            Alert(
                code="api_key_expired",
                severity="critical",
                message=(
                    f"La API key de Garmin caducó hace {abs(context.api_key_days_left)} días."
                ),
                value=float(context.api_key_days_left),
            )
        ]
    return [
        Alert(
            code="api_key_expiring",
            severity="warning",
            message=(
                f"La API key de Garmin caduca en {context.api_key_days_left} días "
                f"(umbral: {API_KEY_WARNING_DAYS})."
            ),
            value=float(context.api_key_days_left),
        )
    ]


def evaluate(context: AlertContext) -> list[Alert]:
    """Ejecuta todas las reglas y conserva un orden estable para el log."""
    alerts: list[Alert] = []
    alerts.extend(acwr_alert(context))
    alerts.extend(inactivity_alert(context))
    alerts.extend(compliance_alert(context))
    alerts.extend(freshness_alert(context))
    alerts.extend(api_key_expiry_alert(context))
    return alerts
