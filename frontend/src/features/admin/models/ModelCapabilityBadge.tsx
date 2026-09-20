// Model Capability Badge Component
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ModelCapabilityBadgeProps {
  capability: 'tools' | 'vision' | 'audio' | 'structured_output';
  supported: boolean | null;
}

export function ModelCapabilityBadge({ capability, supported }: ModelCapabilityBadgeProps) {
  const labels: Record<string, string> = {
    tools: 'Tools',
    vision: 'Vision',
    audio: 'Audio',
    structured_output: 'Structured',
  };

  const icons: Record<string, string> = {
    tools: '🛠️',
    vision: '👁️',
    audio: '🎵',
    structured_output: '📋',
  };

  if (supported === null || supported === undefined) {
    return (
      <Badge variant="secondary" className="text-xs">
        {icons[capability]} {labels[capability]}: ?
      </Badge>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger>
        <Badge 
          variant={supported ? "default" : "outline"} 
          className={`text-xs ${supported ? 'bg-green-600' : 'bg-gray-400'}`}
        >
          {icons[capability]} {labels[capability]}: {supported ? '✓' : '✗'}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <p>{supported ? `Supports ${labels[capability]}` : `Does not support ${labels[capability]}`}</p>
      </TooltipContent>
    </Tooltip>
  );
}
