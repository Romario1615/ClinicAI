import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { Observable } from 'rxjs';

import { ApiService, FalloApi, type AltaClinicaPlataforma } from './api.service';
import { BASE, PROVEEDORES_PRUEBA } from '../pruebas/sesion-sintetica';

describe('ApiService · acceso, gestión y seguimiento', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: PROVEEDORES_PRUEBA });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  function comprobar(solicitud: Observable<unknown>, metodo: string, ruta: string, cuerpo?: unknown) {
    let recibido: unknown;
    solicitud.subscribe(respuesta => recibido = respuesta);
    const peticion = http.expectOne(r => r.method === metodo && r.url === BASE + ruta);
    if (cuerpo !== undefined) expect(peticion.request.body).toEqual(cuerpo);
    const respuesta = { origen: 'Respuesta sintética de API' };
    peticion.flush(respuesta);
    expect(recibido).toEqual(respuesta);
    return peticion.request;
  }

  it('envía la especialidad únicamente cuando se ha seleccionado', () => {
    comprobar(api.iniciarSesionLocal('profesional'), 'POST', '/autenticacion/sesion-local', { codigo_rol: 'profesional' });
    comprobar(api.iniciarSesionLocal('profesional', 'esp-est'), 'POST', '/autenticacion/sesion-local', { codigo_rol: 'profesional', especialidad_id: 'esp-est' });
  });

  it('lista y crea una clínica con sus datos institucionales y sede inicial', () => {
    comprobar(api.clinicasPlataforma(), 'GET', '/plataforma/clinicas');
    const datos: AltaClinicaPlataforma = {
      nombre: 'Clínica sintética', identificacion_fiscal: null, zona_horaria: 'America/Guayaquil',
      idioma: 'es', moneda: 'USD', telefono: null, correo: 'clinica@example.invalid',
      sede_nombre: 'Sede sintética', sede_direccion: null, administrador_nombre: 'Administración',
      administrador_apellido: 'Sintética', administrador_correo: 'admin@example.invalid', contrasena_inicial: 'VALOR_SINTETICO_NO_UTILIZABLE',
    };
    comprobar(api.crearClinicaPlataforma(datos), 'POST', '/plataforma/clinicas', datos);
  });

  it('mantiene la clínica en las rutas de consulta y alta de sedes', () => {
    comprobar(api.sedesPlataforma('cli-1'), 'GET', '/plataforma/clinicas/cli-1/sedes');
    const datos = { nombre: 'Sede sintética', direccion: null, telefono: null, zona_horaria: null };
    comprobar(api.crearSedePlataforma('cli-1', datos), 'POST', '/plataforma/clinicas/cli-1/sedes', datos);
  });

  it('filtra roles y profesionales por clínica y conserva el usuario de la edición', () => {
    comprobar(api.usuariosPlataforma(), 'GET', '/plataforma/clinicas/usuarios');
    expect(comprobar(api.rolesPlataforma('cli-1'), 'GET', '/plataforma/clinicas/roles').params.get('clinica_id')).toBe('cli-1');
    const peticion = comprobar(api.profesionalesPlataforma('cli-1', 'u-1'), 'GET', '/plataforma/clinicas/profesionales');
    expect(peticion.params.get('clinica_id')).toBe('cli-1');
    expect(peticion.params.get('usuario_id')).toBe('u-1');
    expect(comprobar(api.profesionalesPlataforma('cli-1'), 'GET', '/plataforma/clinicas/profesionales').params.has('usuario_id')).toBe(false);
  });

  it('crea el acceso y actualiza la asignación de clínica, perfil y roles', () => {
    const asignacion = { clinica_id: 'cli-1', roles: ['profesional'], profesional_id: 'prof-1', sedes_ids: ['sede-1'] };
    const datos = { ...asignacion, correo: 'persona@example.invalid', nombre: 'Persona', apellido: 'Sintética', contrasena_inicial: 'VALOR_SINTETICO_NO_UTILIZABLE' };
    comprobar(api.crearUsuarioPlataforma(datos), 'POST', '/plataforma/clinicas/usuarios', datos);
    comprobar(api.actualizarAsignacionPlataforma('u-1', asignacion), 'PUT', '/plataforma/clinicas/usuarios/u-1/asignacion', asignacion);
  });

  it('pagina conversaciones y consulta su contador y detalle', () => {
    const peticion = comprobar(api.conversacionesPendientes(25, 50), 'GET', '/conversaciones');
    expect(peticion.params.get('limite')).toBe('25');
    expect(peticion.params.get('desplazamiento')).toBe('50');
    comprobar(api.cuentaConversacionesPendientes(), 'GET', '/conversaciones/pendientes/cuenta');
    comprobar(api.conversacion('conv-1'), 'GET', '/conversaciones/conv-1');
  });

  it('consulta y confirma los avisos de revisión humana del tratamiento', () => {
    comprobar(api.avisosTratamientoPendientes(), 'GET', '/conversaciones/avisos-tratamiento');
    comprobar(api.cuentaAvisosTratamientoPendientes(), 'GET', '/conversaciones/avisos-tratamiento/cuenta');
    comprobar(api.confirmarRevisionAvisoTratamiento('aviso-1'), 'POST', '/conversaciones/avisos-tratamiento/aviso-1/revision', null);
  });

  it('consulta y revisa los avisos de acceso de emergencia', () => {
    comprobar(api.avisosAccesoEmergencia(), 'GET', '/historia/avisos-acceso-emergencia');
    comprobar(api.cuentaAvisosAccesoEmergencia(), 'GET', '/historia/avisos-acceso-emergencia/cuenta');
    comprobar(api.revisarAvisoAccesoEmergencia('aviso-1'), 'POST', '/historia/avisos-acceso-emergencia/aviso-1/revision', null);
  });

  it('envía el motivo de anulación de una imagen y la nota profesional de adherencia', () => {
    comprobar(api.anularImagen('img-1', 'Motivo sintético'), 'PATCH', '/imagenes/img-1/anulacion', { motivo: 'Motivo sintético' });
    comprobar(api.adherencia('rx-1'), 'GET', '/historia/recetas/rx-1/adherencia');
    comprobar(api.atenderAlertaAdherencia('alerta-1', 'Revisión sintética'), 'POST', '/historia/adherencia/alertas/alerta-1/atencion', { nota_profesional: 'Revisión sintética' });
    comprobar(api.atenderAlertaAdherencia('alerta-2'), 'POST', '/historia/adherencia/alertas/alerta-2/atencion', { nota_profesional: null });
  });

  it('mantiene los filtros de sede y profesional al descargar la agenda', () => {
    let recibido: Blob | undefined;
    api.exportarResumenAgenda({ desde: '2026-10-08', hasta: '2026-10-09', sede_id: 'sede-1', profesional_id: 'prof-1' }).subscribe(blob => recibido = blob);
    const peticion = http.expectOne(r => r.url === BASE + '/agenda/resumen.csv');
    expect(peticion.request.responseType).toBe('blob');
    expect(peticion.request.params.get('desde')).toBe('2026-10-08');
    expect(peticion.request.params.get('sede_id')).toBe('sede-1');
    expect(peticion.request.params.get('profesional_id')).toBe('prof-1');
    const archivo = new Blob(['Datos sintéticos'], { type: 'text/csv' });
    peticion.flush(archivo);
    expect(recibido).toBe(archivo);
  });

  it('traduce la sesión caducada conservando su referencia de soporte', () => {
    let error: FalloApi | undefined;
    api.clinicasPlataforma().subscribe({ error: fallo => error = fallo });
    http.expectOne(BASE + '/plataforma/clinicas').flush({ codigo: 'TOKEN_CADUCADO', mensaje: 'Inicie sesión.', correlacion_id: 'referencia-sintetica' }, { status: 401, statusText: 'Unauthorized' });
    expect(error).toBeInstanceOf(FalloApi);
    expect(error?.exigeReautenticacion).toBe(true);
    expect(error?.correlacionId).toBe('referencia-sintetica');
    expect(new FalloApi('FUERA_DE_AMBITO', 'Recurso no disponible.', 404).exigeReautenticacion).toBe(false);
  });
});
