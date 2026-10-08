import { TestBed } from '@angular/core/testing';
import { PeriodoDashboardComponent } from './periodo-dashboard.component';

describe('PeriodoDashboardComponent', () => {
  it('marca el periodo elegido y comunica el cambio mediante un botón accesible', () => {
    const f = TestBed.createComponent(PeriodoDashboardComponent);
    f.componentRef.setInput('periodo', '7');
    const cambio = vi.fn(); f.componentInstance.cambiado.subscribe(cambio);
    f.detectChanges();
    const botones = (f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button');
    expect(botones[1].getAttribute('aria-pressed')).toBe('true');
    expect(botones[0].getAttribute('aria-pressed')).toBe('false');
    botones[2].click(); expect(cambio).toHaveBeenCalledWith('30');
  });
});
