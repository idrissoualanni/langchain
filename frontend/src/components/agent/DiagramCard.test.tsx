// DiagramCard : chart brut requis, caption optionnelle, jamais de crash.
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DiagramCard } from './DiagramCard';

vi.mock('../assistant-ui/elements/mermaid-diagram.aui', () => ({
  MermaidDiagram: ({ chart }: { chart: string }) => (
    <div data-testid="mermaid">{chart}</div>
  ),
}));

describe('DiagramCard', () => {
  it('rend le chart et la caption', () => {
    render(
      <DiagramCard
        data={{ chart: 'flowchart LR\nA-->B', caption: 'Architecture' }}
      />,
    );
    expect(screen.getByTestId('mermaid')).toHaveTextContent('flowchart LR');
    expect(screen.getByText('Architecture')).toBeInTheDocument();
  });

  it('caption absente → libellé par défaut "diagramme"', () => {
    render(<DiagramCard data={{ chart: 'graph TD\nA-->B' }} />);
    expect(screen.getByText('diagramme')).toBeInTheDocument();
  });

  it('chart vide/blanc → null (repli silencieux)', () => {
    const { container } = render(<DiagramCard data={{ chart: '  ' }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('data undefined → pas de crash, null', () => {
    const { container } = render(
      <DiagramCard data={undefined as never} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
