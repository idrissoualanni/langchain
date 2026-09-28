// Tests du contrat V6.7 : ResponseRenderer route chaque type vers la
// bonne carte, sans jamais crasher sur un payload inattendu.
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AgentResponse } from '../../types/agentResponse';
import { ResponseRenderer } from './ResponseRenderer';

const base = (over: Partial<AgentResponse>): AgentResponse => ({
  version: 1,
  type: 'text',
  status: 'completed',
  message: '',
  data: {},
  actions: [],
  ...over,
});

// MermaidDiagram charge le module `mermaid` (lourd, DOM) → mock.
vi.mock('../assistant-ui/elements/mermaid-diagram.aui', () => ({
  MermaidDiagram: ({ chart }: { chart: string }) => (
    <div data-testid="mermaid">{chart}</div>
  ),
}));

describe('ResponseRenderer', () => {
  it('type text → aucun rendu (le part text officiel rend déjà)', () => {
    const { container } = render(<ResponseRenderer response={base({})} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('type diagram → DiagramCard avec le chart brut', () => {
    render(
      <ResponseRenderer
        response={base({
          type: 'diagram',
          data: { chart: 'graph TB\nA-->B', caption: 'Pipeline RAG' },
        })}
      />,
    );
    expect(screen.getByTestId('mermaid')).toHaveTextContent('graph TB');
    expect(screen.getByText('Pipeline RAG')).toBeInTheDocument();
  });

  it('diagram sans chart exploitable → repli silencieux (pas de crash)', () => {
    const { container } = render(
      <ResponseRenderer
        response={base({ type: 'diagram', data: { chart: '   ' } })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('type quiz → progression question i/N', () => {
    render(
      <ResponseRenderer
        response={base({
          type: 'quiz',
          data: {
            activity_id: 'a1',
            activity_status: 'waiting_for_answer',
            question_index: 2,
            total_questions: 5,
          },
        })}
      />,
    );
    expect(screen.getByText('quiz')).toBeInTheDocument();
    expect(screen.getByText(/question 3\/5/)).toBeInTheDocument();
  });

  it('type error → badge erreur', () => {
    render(<ResponseRenderer response={base({ type: 'error' })} />);
    expect(screen.getByText('erreur')).toBeInTheDocument();
  });

  it('type clarification → boutons options + callback', async () => {
    const onOption = vi.fn();
    render(
      <ResponseRenderer
        response={base({
          type: 'clarification',
          actions: [{ type: 'select', options: ['Python', 'JavaScript'] }],
        })}
        onOption={onOption}
      />,
    );
    screen.getByRole('button', { name: 'Python' }).click();
    expect(onOption).toHaveBeenCalledWith('Python');
  });

  it('type search → liste des sources', () => {
    render(
      <ResponseRenderer
        response={base({
          type: 'search',
          data: {
            result_count: 1,
            results: [
              {
                title: 'Doc Officielle',
                source: 'docs.example.com',
                url: 'https://docs.example.com/x',
                snippet: 'extrait',
              },
            ],
          },
        })}
      />,
    );
    expect(screen.getByText('sources')).toBeInTheDocument();
    expect(screen.getByText('Doc Officielle')).toBeInTheDocument();
  });

  it('type inconnu → aucune exception, rien rendu', () => {
    const { container } = render(
      <ResponseRenderer
        response={base({ type: 'future_type' as AgentResponse['type'] })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
