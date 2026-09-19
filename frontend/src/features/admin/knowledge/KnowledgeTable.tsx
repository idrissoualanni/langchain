// Knowledge Table Component
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreVertical, Pencil, Trash2, Shield } from "lucide-react";
import { KnowledgeStatusBadge } from "./KnowledgeStatusBadge";

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  scope: 'public' | 'private' | 'group' | 'user' | 'admin';
  group_ids?: string[];
  owner_user_id?: string;
  document_count?: number;
  enabled: boolean;
}

interface KnowledgeTableProps {
  knowledgeBases: KnowledgeBase[];
  onEdit: (kb: KnowledgeBase) => void;
  onDelete: (kbId: string) => void;
  onManageAccess: (kb: KnowledgeBase) => void;
}

export function KnowledgeTable({ 
  knowledgeBases, 
  onEdit, 
  onDelete, 
  onManageAccess 
}: KnowledgeTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>ID</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Scope</TableHead>
          <TableHead>Documents</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {knowledgeBases.map((kb) => (
          <TableRow key={kb.id}>
            <TableCell className="font-mono text-sm">{kb.id}</TableCell>
            <TableCell>
              <div>
                <div className="font-medium">{kb.name}</div>
                {kb.description && (
                  <div className="text-sm text-muted-foreground truncate max-w-md">
                    {kb.description}
                  </div>
                )}
              </div>
            </TableCell>
            <TableCell>
              <KnowledgeStatusBadge 
                scope={kb.scope} 
                groupIds={kb.group_ids}
                ownerUserId={kb.owner_user_id}
              />
            </TableCell>
            <TableCell>
              <span className="text-sm text-muted-foreground">
                {kb.document_count || 0} docs
              </span>
            </TableCell>
            <TableCell>
              <span className={`text-sm ${kb.enabled ? 'text-green-600' : 'text-red-600'}`}>
                {kb.enabled ? 'Active' : 'Disabled'}
              </span>
            </TableCell>
            <TableCell className="text-right">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onManageAccess(kb)}>
                    <Shield className="mr-2 h-4 w-4" />
                    Manage Access
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onEdit(kb)}>
                    <Pencil className="mr-2 h-4 w-4" />
                    Edit
                  </DropdownMenuItem>
                  <DropdownMenuItem 
                    onClick={() => onDelete(kb.id)}
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
