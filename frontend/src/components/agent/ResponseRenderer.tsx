// ResponseRenderer V6.7 (§27) — rend une AgentResponse selon
// response.type. Le frontend ne PARSE JAMAIS le texte (§18) :
// la nature de la réponse vient du contrat structuré backend.
//
// Le TEXTE de la réponse est rendu par le part text officiel
// (MessagePrimitive.Parts → MarkdownText assistant-ui), pas ici :
// les types 'text'/inconnus ne produisent donc aucun rendu
// (sinon le message apparaîtrait deux fois). Les cartes ne
// rendent que leur contenu STRUCTURÉ.
import type {
  AgentResponse,
  CodeData,
  DiagramData,
  EvaluationData,
  ExerciseData,
  HintData,
  QuizData,
  SearchData,
} from '../../types/agentResponse';
import { ClarificationCard } from './ClarificationCard';
import { CodeActivityCard } from './CodeActivityCard';
import { DiagramCard } from './DiagramCard';
import { ErrorCard } from './ErrorCard';
import { EvaluationCard } from './EvaluationCard';
import { ExerciseCard } from './ExerciseCard';
import { HintCard } from './HintCard';
import { QuizCard } from './QuizCard';
import { SearchResultCard } from './SearchResultCard';
import { IllustrationCard } from '../assistant-ui/elements/illustration-card';
import { StyledTable } from '../assistant-ui/elements/styled-table';

export function ResponseRenderer({
  response,
  onAction,
  onOption,
  threadId,
  userId,
}: {
  response: AgentResponse;
  onAction?: (type: string) => void;
  onOption?: (option: string) => void;
  threadId?: string | null;
  userId?: string | null;
}) {
  const { type, status, data, actions } = response;

  switch (type) {
    case 'text':
      // Texte rendu par le part text officiel.
      return null;

    case 'exercise':
      return (
        <ExerciseCard
          data={data as unknown as ExerciseData}
          actions={actions}
          onAction={onAction}
        />
      );

    case 'quiz':
      return <QuizCard data={data as unknown as QuizData} />;

    case 'evaluation':
      return (
        <EvaluationCard
          data={data as unknown as EvaluationData}
          status={status}
        />
      );

    case 'hint':
      return <HintCard data={data as unknown as HintData} />;

    case 'code':
      return (
        <CodeActivityCard
          data={data as unknown as CodeData}
          threadId={threadId ?? null}
          userId={userId ?? null}
        />
      );

    case 'diagram':
      return <DiagramCard data={data as unknown as DiagramData} />;

    case 'illustration':
      return (
        <IllustrationCard
          id={response.id || 'illustration-default'}
          type={(data as any).type || 'image'}
          title={(data as any).title}
        >
          {/* On délègue le rendu du contenu à un composant interne ou on utilise
              les données structurées ici. Si data contient un tableau, on utilise
              StyledTable, sinon on peut utiliser DiagramCard pour Mermaid. */}
          {(data as any).type === 'table' ? (
            <StyledTable
              data={(data as any).rows || []}
              columns={(data as any).columns || []}
            />
          ) : (data as any).type === 'diagram' ? (
            <DiagramCard data={data as any} />
          ) : (
            <div className="text-sm text-muted-foreground italic">
              Illustration non supportée ou contenu manquant
            </div>
          )}
        </IllustrationCard>
      );

    case 'search':
      return <SearchResultCard data={data as unknown as SearchData} />;

    case 'clarification':
      return (
        <ClarificationCard actions={actions} onAction={onOption} />
      );

    case 'error':
      return <ErrorCard />;

    default:
      // Défense : type inconnu → rien (le texte est déjà rendu
      // par le part text officiel ; jamais de crash UI).
      return null;
  }
}
