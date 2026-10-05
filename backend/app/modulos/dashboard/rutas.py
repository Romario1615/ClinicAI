import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import select

from app.modulos.dashboard.esquemas import AnalisisInteligente, FiltroDashboard, ResumenDashboard
from app.modulos.dashboard.repositorio import resumir
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, CifradorActual, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos, ProveedorExternoNoDisponible, ReglaNegocioViolada

enrutador = APIRouter(prefix="/dashboard", tags=["dashboard"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("dashboard.leer"))]
PuedeAnalizar = Annotated[
    Principal,
    Depends(exige_permiso("dashboard.leer", "configuracion.escribir", exigir_todos=True)),
]


def filtro_dashboard(desde: AwareDatetime, hasta: AwareDatetime) -> FiltroDashboard:
    """Construye el filtro traduciendo el fallo de validacion a `DatosInvalidos`.

    No se declara el modelo como `Depends()` directamente: cuando su
    `model_validator` rechaza el rango, FastAPI **no** convierte esa excepcion
    en un 422 -- solo traduce los fallos de su propio analisis de la peticion --
    y el error escapa como un 500. Un rango invertido es entrada invalida del
    cliente, no una averia del servidor, y tiene que salir con el contrato de
    error del proyecto como el resto de los endpoints.
    """
    try:
        return FiltroDashboard(desde=desde, hasta=hasta)
    except ValidationError as exc:
        primero = exc.errors()[0]
        raise DatosInvalidos(str(primero.get("msg", "Rango de fechas invalido."))) from exc


@enrutador.get("/", response_model=ResumenDashboard)
async def resumen(
    principal: PuedeLeer,
    sesion: Sesion,
    filtro: Annotated[FiltroDashboard, Depends(filtro_dashboard)],
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
) -> ResumenDashboard:
    return await resumir(sesion, principal, filtro, sede_id, profesional_id)


@enrutador.post("/analisis-ia", response_model=AnalisisInteligente)
async def analizar_con_ia(
    principal: PuedeAnalizar,
    sesion: Sesion,
    cifrador: CifradorActual,
    auditor: Auditor,
    reloj: RelojActual,
    filtro: Annotated[FiltroDashboard, Depends(filtro_dashboard)],
) -> AnalisisInteligente:
    """Analiza métricas agregadas con el proveedor que habilitó la clínica."""
    if principal.clinica_id is None:
        raise ReglaNegocioViolada("La sesión no tiene una clínica asociada.")
    clave_integracion = "integracion.anthropic"
    fila = (
        await sesion.execute(
            select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == principal.clinica_id,
                ConfiguracionClinica.clave == clave_integracion,
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()
    valor: dict[str, Any] = fila.valor if fila is not None and isinstance(fila.valor, dict) else {}
    secretos_valor = valor.get("secretos_cifrados", {})
    ajustes_valor = valor.get("ajustes", {})
    secretos: dict[str, Any] = secretos_valor if isinstance(secretos_valor, dict) else {}
    ajustes: dict[str, Any] = ajustes_valor if isinstance(ajustes_valor, dict) else {}
    secreto_cifrado = secretos.get("api_key")
    if valor.get("habilitada") is not True or not secreto_cifrado:
        raise ReglaNegocioViolada(
            "Active Anthropic y guarde su clave en Configuración de la clínica."
        )
    try:
        api_key = cifrador.descifrar(
            secreto_cifrado,
            contexto=b"integracion:" + principal.clinica_id.bytes + b":anthropic:api_key",
        )
    except ValueError as exc:
        raise ProveedorExternoNoDisponible(
            "No se pudo leer la credencial de IA configurada."
        ) from exc

    datos = await resumir(sesion, principal, filtro)
    agregado = {
        "periodo": {"desde": filtro.desde.isoformat(), "hasta": filtro.hasta.isoformat()},
        "total_citas": datos.total_citas,
        "pacientes_distintos": datos.pacientes,
        "estados_de_cita": datos.citas,
        "espera": datos.espera.model_dump(),
        "totales_de_pago_por_estado": (
            {estado: str(importe) for estado, importe in datos.pagos.items()}
            if datos.pagos is not None
            else None
        ),
    }
    try:
        from anthropic import AsyncAnthropic  # noqa: PLC0415

        async with AsyncAnthropic(api_key=api_key, timeout=20, max_retries=0) as cliente:
            respuesta = await cliente.messages.create(
                model=str(ajustes.get("modelo", "claude-sonnet-5")),
                max_tokens=min(int(ajustes.get("max_tokens", 2048)), 1200),
                temperature=float(ajustes.get("temperatura", 0.2)),
                system=(
                    "Eres un analista operativo para administradores de clínicas. "
                    "Resume señales, tendencias y acciones administrativas posibles usando solo "
                    "las métricas proporcionadas. No hagas diagnósticos ni recomendaciones clínicas. "
                    "No afirmes causalidad ni inventes comparaciones ausentes. Responde en español, "
                    "con máximo cuatro viñetas y lenguaje claro."
                ),
                messages=[{"role": "user", "content": json.dumps(agregado, ensure_ascii=False)}],
            )
        fragmentos: list[str] = []
        for bloque in respuesta.content:
            texto = getattr(bloque, "text", None)
            if isinstance(texto, str):
                fragmentos.append(texto)
        analisis = "\n".join(fragmentos).strip()
        if not analisis:
            raise ValueError("Respuesta vacía del proveedor.")
    except Exception as exc:
        # La respuesta de terceros nunca expone URL, clave, encabezados ni traza.
        raise ProveedorExternoNoDisponible(
            "No se pudo generar el análisis de seguimiento."
        ) from exc

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.DASHBOARD_ANALISIS_IA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="dashboard",
                entidad_id=principal.clinica_id,
                desde=filtro.desde.isoformat(),
                hasta=filtro.hasta.isoformat(),
                proveedor="anthropic",
            )
        ]
    )
    await sesion.commit()
    return AnalisisInteligente(analisis=analisis)
