import { TestBed } from '@angular/core/testing';
import { ChatConversacionalComponent } from './chat-conversacional.component';

describe('Formulario compartido del chat', () => {
  function montar(texto: string, ocupado = false, deshabilitado = false) {
    TestBed.configureTestingModule({ imports: [ChatConversacionalComponent] });
    const fixture = TestBed.createComponent(ChatConversacionalComponent);
    fixture.componentRef.setInput('texto', texto);
    fixture.componentRef.setInput('ocupado', ocupado);
    fixture.componentRef.setInput('deshabilitado', deshabilitado);
    const enviar = vi.fn();
    fixture.componentInstance.enviar.subscribe(enviar);
    fixture.detectChanges();
    return { fixture, enviar, textarea: fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement };
  }

  it('la región de conversación incluye el registro de mensajes y su formulario', () => {
    const { fixture } = montar('Consulta sintética');
    expect(fixture.nativeElement.getAttribute('role')).toBe('region');
    expect(fixture.nativeElement.getAttribute('aria-label')).toBe('Conversación');
    expect(fixture.nativeElement.querySelector('[role="log"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('form textarea')).not.toBeNull();
  });

  it.each([
    ['', false, false], ['   ', false, false], ['Mensaje', true, false], ['Mensaje', false, true], ['x'.repeat(1001), false, false],
  ] as const)('Enter y submit respetan el estado del formulario: %s, %s, %s', (texto, ocupado, deshabilitado) => {
    const { fixture, enviar, textarea } = montar(texto, ocupado, deshabilitado);
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    expect(enviar).not.toHaveBeenCalled();
  });

  it('Enter envía el mensaje y Shift+Enter permite una nueva línea', () => {
    const { enviar, textarea } = montar('Consulta sintética');
    const salto = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true });
    textarea.dispatchEvent(salto);
    expect(salto.defaultPrevented).toBe(false);
    expect(enviar).not.toHaveBeenCalled();
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    expect(enviar).toHaveBeenCalledOnce();
  });

  it('Enter durante composición no envía un mensaje incompleto', () => {
    const { enviar, textarea } = montar('Consulta sintética');
    const evento = new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true });
    textarea.dispatchEvent(evento);
    expect(enviar).not.toHaveBeenCalled();
    expect(evento.defaultPrevented).toBe(false);
  });
});
