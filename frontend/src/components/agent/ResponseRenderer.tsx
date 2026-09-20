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
  EvaluationData,
  ExerciseData,
  HintData,
  QuizData,
  SearchData,
} from '../../types/agentResponse';
import { ClarificationCard } from './ClarificationCard';
import { CodeActivityCard } from './CodeActivityCard';
import { ErrorCard } from './ErrorCard';
import { EvaluationCard } from './EvaluationCard';
import { ExerciseCard } from './ExerciseCard';
import { HintCard } from './HintCard';
import { QuizCard } from './QuizCard';
import { SearchResultCard } from './SearchResultCard';

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
