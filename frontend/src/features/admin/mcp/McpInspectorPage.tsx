// Inspecteur MCP — page d'administration (§39/§40/§41).
//
// À quoi ça sert : voir quels serveurs MCP existent, quels tools ils
// exposent, quel JSON ils attendent, et les exécuter pour de vrai afin
// de déboguer un workflow. C'est l'équivalent de MCP Inspector, mais
// branché sur NOTRE infra (registre, serveurs stdio, identité admin).
//
// Garde-fou principal : les tools qui écrivent (create_file, write_file,
// create_event…) demandent une confirmation explicite. Les tools de
// lecture s'exécutent directement — rejouer un `list_files` est sans
// conséquence, tandis qu'écraser un fichier ne l'est pas.
import { useMemo, useState } from 'react';
import { RefreshCw, Server, Play, AlertTriangle, TerminalSquare, FileWarning } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Dialog } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { ErrorState } from '@/components/ui/error-state';
import { LoadingState } from '@/components/ui/loading-state';
import { cn } from '@/lib/utils';
import { useMcpInspector } from './useMcp';
import type { McpContentBlock, McpInvokeResult, McpTool } from './mcpApi';

/** Tools d'écriture connus. Sert de premier filtre, avant l'heuristique. */
const WRITE_TOOLS = new Set([
  'create_file',
  'write_file',
  'delete_file',
  'create_event',
  'update_event',
  'delete_event',
]);

/** Un tool est-il mutant ? Confirmation obligatoire si oui. */
function isMutating(toolName: string): boolean {
  if (WRITE_TOOLS.has(toolName)) return true;
  return /^(create|write|update|delete|remove|set|add|append|move|rename|put)_/i.test(toolName);
}

/** Génère un squelette d'arguments à partir du JSON Schema d'entrée.
 *
 * Rend l'inspecteur utilisable en 2 clics : on pré-remplit le type
 * attendu de chaque champ, l'utilisateur remplace les valeurs. */
function templateFromSchema(schema: Record<string, unknown>): Record<string, unknown> {
  const props = (schema?.properties ?? {}) as Record<string, { type?: string; default?: unknown }>;
  const out: Record<string, unknown> = {};
  for (const [key, def] of Object.entries(props)) {
    if (def && 'default' in def && def.default !== undefined) {
      out[key] = def.default;
      continue;
    }
    switch (def?.type) {
      case 'string':
        out[key] = '';
        break;
      case 'number':
      case 'integer':
        out[key] = 0;
        break;
      case 'boolean':
        out[key] = false;
        break;
      case 'array':
        out[key] = [];
        break;
      case 'object':
        out[key] = {};
        break;
      default:
        out[key] = null;
    }
  }
  return out;
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function blockText(block: McpContentBlock): string {
  if (typeof block.text === 'string') return block.text;
  if (typeof block.repr === 'string') return block.repr;
  return '';
}

export function McpInspectorPage() {
  const mcp = useMcpInspector();
  const [selectedTool, setSelectedTool] = useState<McpTool | null>(null);
  const [argsJson, setArgsJson] = useState('{}');
  const [argsError, setArgsError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleSelectServer = (name: string) => {
    mcp.selectServer(name);
    setSelectedTool(null);
    setArgsJson('{}');
    setArgsError(null);
  };

  const handleSelectTool = (tool: McpTool) => {
    setSelectedTool(tool);
    setArgsJson(pretty(templateFromSchema(tool.input_schema)));
    setArgsError(null);
    mcp.clearResult();
  };

  const parseArgs = (): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(argsJson || '{}');
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setArgsError("Les arguments doivent être un objet JSON, par exemple {\"path\": \"notes.md\"}.");
        return null;
      }
      setArgsError(null);
      return parsed as Record<string, unknown>;
    } catch (err) {
      setArgsError(`JSON invalide : ${err instanceof Error ? err.message : String(err)}`);
      return null;
    }
  };

  const run = async () => {
    if (!selectedTool) return;
    const args = parseArgs();
    if (!args) return;
    await mcp.invoke(selectedTool.name, args);
  };

  const requestRun = () => {
    if (!selectedTool) return;
    if (isMutating(selectedTool.name)) {
      setConfirmOpen(true);
      return;
    }
    void run();
  };

  const mutating = useMemo(
    () => (selectedTool ? isMutating(selectedTool.name) : false),
    [selectedTool]
  );

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Inspecteur MCP</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Explorez les serveurs MCP autorisés et exécutez leurs outils pour déboguer un workflow.
            Le navigateur ne parle jamais MCP directement : chaque action passe par le backend, qui
            pilote les serveurs stdio avec ton identité.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void mcp.reloadServers()}
          disabled={mcp.serversLoading}
        >
          <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', mcp.serversLoading && 'animate-spin')} />
          Rafraîchir
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Colonne serveurs */}
        <div className="space-y-3 lg:col-span-1">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Server className="h-3.5 w-3.5" /> Serveurs autorisés
          </h2>

          {mcp.serversLoading && <LoadingState label="Chargement des serveurs…" />}

          {!mcp.serversLoading && mcp.serversError && (
            <ErrorState
              title="Serveurs indisponibles"
              message={mcp.serversError}
              onRetry={() => void mcp.reloadServers()}
            />
          )}

          {!mcp.serversLoading && !mcp.serversError && mcp.servers.length === 0 && (
            <EmptyState
              icon={<Server />}
              title="Aucun serveur MCP déclaré"
              description="Le registre ne contient aucun serveur. Vérifie la configuration MCP du backend."
            />
          )}

          {mcp.servers.map((srv) => {
            const active = mcp.server === srv.name;
            return (
              <button
                key={srv.name}
                type="button"
                onClick={() => handleSelectServer(srv.name)}
                className={cn(
                  'w-full rounded-[var(--radius-document)] border p-3 text-left transition-colors',
                  active
                    ? 'border-live/40 bg-live/5'
                    : 'border-border bg-card hover:border-foreground/20'
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">{srv.name}</span>
                  <Badge tone={srv.enabled ? 'success' : 'warning'}>
                    {srv.enabled ? 'actif' : 'désactivé'}
                  </Badge>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">{srv.description}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {srv.capabilities.map((cap) => (
                    <Badge key={cap} tone="ghost" className="font-mono text-[10px]">
                      {cap}
                    </Badge>
                  ))}
                </div>
                <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                  timeout {srv.timeout_s}s · {srv.rate_limit ? `${srv.rate_limit}/min` : 'sans limite'}
                  {srv.allowed_workflows.length > 0 && ` · workflows: ${srv.allowed_workflows.join(', ')}`}
                </p>
              </button>
            );
          })}
        </div>

        {/* Colonne tools + exécution */}
        <div className="space-y-4 lg:col-span-2">
          {!mcp.server && (
            <EmptyState
              icon={<TerminalSquare />}
              title="Sélectionnez un serveur"
              description="Choisis un serveur à gauche pour afficher ses outils et les exécuter."
            />
          )}

          {mcp.server && (
            <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <TerminalSquare className="h-3.5 w-3.5" /> Outils de « {mcp.server} »
            </h2>
          )}

          {mcp.server && mcp.toolsLoading && (
            <LoadingState label={`Démarrage du serveur « ${mcp.server} »…`} />
          )}

          {mcp.server && !mcp.toolsLoading && mcp.toolsError && (
            <ErrorState
              title="Serveur injoignable"
              message={mcp.toolsError}
              details={mcp.toolsError}
              onRetry={() => void mcp.reloadTools()}
            />
          )}

          {mcp.server && !mcp.toolsLoading && !mcp.toolsError && (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {/* Liste des tools */}
              <div className="space-y-2">
                {mcp.tools.map((tool) => {
                  const active = selectedTool?.name === tool.name;
                  const writes = isMutating(tool.name);
                  return (
                    <button
                      key={tool.name}
                      type="button"
                      onClick={() => handleSelectTool(tool)}
                      className={cn(
                        'w-full rounded-[var(--radius-document)] border p-3 text-left transition-colors',
                        active
                          ? 'border-live/40 bg-live/5'
                          : 'border-border bg-card hover:border-foreground/20'
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm font-medium text-foreground">
                          {tool.name}
                        </span>
                        <Badge tone={writes ? 'warning' : 'default'}>
                          {writes ? 'écriture' : 'lecture'}
                        </Badge>
                      </div>
                      {tool.description && (
                        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                          {tool.description}
                        </p>
                      )}
                    </button>
                  );
                })}

                {mcp.tools.length === 0 && (
                  <EmptyState
                    icon={<TerminalSquare />}
                    title="Aucun outil exposé"
                    description="Ce serveur a démarré mais ne déclare aucun outil."
                  />
                )}
              </div>

              {/* Panneau d'exécution */}
              <div className="space-y-3">
                {!selectedTool && (
                  <EmptyState
                    icon={<Play />}
                    title="Choisis un outil"
                    description="Les outils d'écriture demanderont une confirmation avant de s'exécuter."
                  />
                )}

                {selectedTool && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <span className="font-mono">{selectedTool.name}</span>
                        <Badge tone={mutating ? 'warning' : 'default'}>
                          {mutating ? 'écriture' : 'lecture'}
                        </Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {mutating && (
                        <p className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground/80">
                          <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                          Cet outil modifie des données. Vérifie les arguments, une confirmation te
                          sera demandée.
                        </p>
                      )}

                      <div>
                        <label
                          htmlFor="mcp-args"
                          className="mb-1 block font-mono text-[11px] uppercase tracking-wide text-muted-foreground"
                        >
                          Arguments (JSON)
                        </label>
                        <Textarea
                          id="mcp-args"
                          value={argsJson}
                          onChange={(e) => setArgsJson(e.target.value)}
                          spellCheck={false}
                          rows={9}
                          className="font-mono text-xs"
                        />
                        {argsError && (
                          <p className="mt-1 text-xs text-destructive">{argsError}</p>
                        )}
                        <div className="mt-2 flex items-center justify-between">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setArgsJson(pretty(templateFromSchema(selectedTool.input_schema)));
                              setArgsError(null);
                            }}
                          >
                            Réinitialiser le squelette
                          </Button>
                          <Button size="sm" onClick={requestRun} disabled={mcp.invoking}>
                            <Play className="mr-1.5 h-3.5 w-3.5" />
                            {mcp.invoking ? 'Exécution…' : 'Exécuter'}
                          </Button>
                        </div>
                      </div>

                      <details className="rounded-md border border-border bg-muted/20 p-2">
                        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                          Schéma d'entrée
                        </summary>
                        <pre className="mt-2 max-h-56 overflow-auto font-mono text-[11px] leading-relaxed text-muted-foreground">
                          {pretty(selectedTool.input_schema)}
                        </pre>
                      </details>
                    </CardContent>
                  </Card>
                )}

                {mcp.invokeError && (
                  <ErrorState
                    title="Exécution impossible"
                    message={mcp.invokeError}
                    details={mcp.invokeError}
                  />
                )}

                {mcp.result && <InvokeResult result={mcp.result} />}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation des outils d'écriture */}
      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirmer l'exécution"
      >
        <div className="space-y-3 text-sm">
          <p className="flex items-start gap-2 text-foreground">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <span>
              L'outil <span className="font-mono font-medium">{selectedTool?.name}</span> peut
              modifier des données réelles sur le serveur{' '}
              <span className="font-mono font-medium">{mcp.server}</span>.
            </span>
          </p>
          <pre className="max-h-56 overflow-auto rounded-md bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
            {argsJson}
          </pre>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setConfirmOpen(false)}>
              Annuler
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setConfirmOpen(false);
                void run();
              }}
            >
              Confirmer et exécuter
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

/** Rendu du résultat d'un tool : statut, durée, contenu, JSON structuré. */
function InvokeResult({ result }: { result: McpInvokeResult }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Badge tone={result.ok ? 'success' : 'error'}>
            {result.ok ? 'succès' : 'erreur'}
          </Badge>
          <span className="font-mono text-xs text-muted-foreground">{result.tool}</span>
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            {result.duration_ms} ms
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {result.error && (
          <pre className="max-h-40 overflow-auto rounded-md border border-destructive/30 bg-destructive/5 p-3 font-mono text-[11px] leading-relaxed text-destructive">
            {result.error}
          </pre>
        )}

        {result.content.map((block, i) => {
          const text = blockText(block);
          if (!text) return null;
          return (
            <div key={i}>
              <p className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                {block.type}
              </p>
              <pre className="max-h-72 overflow-auto rounded-md bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-foreground/90">
                {text}
              </pre>
            </div>
          );
        })}

        {result.structured_content && (
          <div>
            <p className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
              structured
            </p>
            <pre className="max-h-72 overflow-auto rounded-md bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-foreground/90">
              {pretty(result.structured_content)}
            </pre>
          </div>
        )}

        {!result.error && result.content.length === 0 && !result.structured_content && (
          <p className="text-xs text-muted-foreground">Aucun contenu renvoyé.</p>
        )}
      </CardContent>
    </Card>
  );
}
