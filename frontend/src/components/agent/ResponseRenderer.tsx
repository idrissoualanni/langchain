// ResponseRenderer V6.7 (§27) — rend une AgentResponse selon
// response.type. Le frontend ne PARSE JAMAIS le texte (§18) :
// la nature de la réponse vient du contrat structuré backend.
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
import { TextResponse } from './TextResponse';

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
  const { type, status, message, data, actions } = response;

  switch (type) {
    case 'text':
      return <TextResponse message={message} />;

    case 'exercise':
      return (
        <ExerciseCard
          message={message}
          data={data as unknown as ExerciseData}
          actions={actions}
          onAction={onAction}
        />
      );

    case 'quiz':
      return (
        <QuizCard
          message={message}
          data={data as unknown as QuizData}
        />
      );

    case 'evaluation':
      return (
        <EvaluationCard
          message={message}
          data={data as unknown as EvaluationData}
          status={status}
        />
      );

    case 'hint':
      return (
        <HintCard
          message={message}
          data={data as unknown as HintData}
        />
      );

    case 'code':
      return (
        <CodeActivityCard
          message={message}
          data={data as unknown as CodeData}
          threadId={threadId ?? null}
          userId={userId ?? null}
        />
      );

    case 'search':
      return (
        <SearchResultCard
          message={message}
          data={data as unknown as SearchData}
        />
      );

    case 'clarification':
      return (
        <ClarificationCard
          message={message}
          actions={actions}
          onAction={onOption}
        />
      );

    case 'error':
      return <ErrorCard message={message} />;

    default: {
      // Défense : type inconnu → texte (jamais de crash UI).
      // L'union AgentResponseType est exhaustive ; ce cas ne
      // sert qu'à la résilience runtime (payload backend futur).
      return <TextResponse message={message} />;
    }
  }
}
