// Knowledge Status Badge Component
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface KnowledgeStatusBadgeProps {
  scope: 'public' | 'private' | 'group' | 'user' | 'admin';
  groupIds?: string[];
  ownerUserId?: string;
}

export function KnowledgeStatusBadge({ scope, groupIds, ownerUserId }: KnowledgeStatusBadgeProps) {
  const getBadgeInfo = () => {
    switch (scope) {
      case 'public':
        return {
          label: 'Public',
          variant: 'default' as const,
          icon: '🌍',
          tooltip: 'Accessible by all users',
        };
      case 'private':
        return {
          label: 'Private',
          variant: 'secondary' as const,
          icon: '🔒',
          tooltip: 'Only accessible by owner',
        };
      case 'group':
        return {
          label: `Group (${groupIds?.length || 0})`,
          variant: 'outline' as const,
          icon: '👥',
          tooltip: `Accessible by groups: ${groupIds?.join(', ') || 'none'}`,
        };
      case 'user':
        return {
          label: 'User',
          variant: 'outline' as const,
          icon: '👤',
          tooltip: `Accessible by user: ${ownerUserId || 'none'}`,
        };
      case 'admin':
        return {
          label: 'Admin',
          variant: 'destructive' as const,
          icon: '🛡️',
          tooltip: 'Admin only access',
        };
      default:
        return {
          label: scope,
          variant: 'secondary' as const,
          icon: '❓',
          tooltip: 'Unknown scope',
        };
    }
  };

  const info = getBadgeInfo();

  return (
    <Tooltip>
      <TooltipTrigger>
        <Badge variant={info.variant}>
          {info.icon} {info.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <p>{info.tooltip}</p>
      </TooltipContent>
    </Tooltip>
  );
}
