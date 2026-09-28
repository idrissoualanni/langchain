// Model Table Component
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreVertical, Pencil, Trash2, Play } from "lucide-react";
import type { ModelConfig } from "@/types";
import { ModelCapabilityBadge } from "./ModelCapabilityBadge";

interface ModelTableProps {
  models: ModelConfig[];
  onEdit: (model: ModelConfig) => void;
  onDelete: (modelId: string) => void;
  onToggle: (modelId: string, enabled: boolean) => void;
  onTest: (modelId: string) => void;
  onSetDefault?: (modelId: string) => void;
}

export function ModelTable({ 
  models, 
  onEdit, 
  onDelete, 
  onToggle, 
  onTest,
  onSetDefault 
}: ModelTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>ID</TableHead>
          <TableHead>Display Name</TableHead>
          <TableHead>Provider</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Capabilities</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {models.map((model) => (
          <TableRow key={model.id}>
            <TableCell className="font-mono text-sm">{model.id}</TableCell>
            <TableCell>{model.display_name || model.id}</TableCell>
            <TableCell>
              <Badge variant="outline">{model.provider}</Badge>
            </TableCell>
            <TableCell className="font-mono text-sm">{model.model_name}</TableCell>
            <TableCell>
              <div className="flex gap-1 flex-wrap">
                {model.capabilities?.supports_tools && (
                  <ModelCapabilityBadge capability="tools" supported={true} />
                )}
                {model.capabilities?.supports_vision && (
                  <ModelCapabilityBadge capability="vision" supported={true} />
                )}
                {model.capabilities?.supports_audio && (
                  <ModelCapabilityBadge capability="audio" supported={true} />
                )}
                {model.capabilities?.supports_structured_output && (
                  <ModelCapabilityBadge capability="structured_output" supported={true} />
                )}
              </div>
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <Switch
                  checked={model.enabled}
                  onCheckedChange={(checked) => onToggle(model.id, checked)}
                />
                <Badge variant={model.enabled ? "default" : "secondary"}>
                  {model.enabled ? "Active" : "Disabled"}
                </Badge>
              </div>
            </TableCell>
            <TableCell className="text-right">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onTest(model.id)}>
                    <Play className="mr-2 h-4 w-4" />
                    Test
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onEdit(model)}>
                    <Pencil className="mr-2 h-4 w-4" />
                    Edit
                  </DropdownMenuItem>
                  {onSetDefault && (
                    <DropdownMenuItem onClick={() => onSetDefault(model.id)}>
                      Set as Default
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem 
                    onClick={() => onDelete(model.id)}
                    className="text-red-600"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
