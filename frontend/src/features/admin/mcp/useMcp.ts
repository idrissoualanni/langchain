// Hook — état de l'Inspecteur MCP.
//
// Regroupe tout ce que la page doit savoir : inventaire des serveurs,
// tools du serveur sélectionné, exécution d'un tool. Chaque appel
// réseau est isolé dans son triplet { loading, error, data } pour que
// l'UI puisse afficher un état utile plutôt qu'un écran vide.
import { useCallback, useEffect, useState } from 'react';
import {
  fetchMcpServers,
  fetchMcpTools,
  invokeMcpTool,
  type McpInvokeResult,
  type McpServer,
  type McpTool,
} from './mcpApi';

export function useMcpInspector() {
  // Inventaire des serveurs.
  const [servers, setServers] = useState<McpServer[]>([]);
  const [serversLoading, setServersLoading] = useState(true);
  const [serversError, setServersError] = useState<string | null>(null);

  // Serveur sélectionné + ses tools.
  const [server, setServer] = useState<string | null>(null);
  const [tools, setTools] = useState<McpTool[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);

  // Exécution d'un tool.
  const [invoking, setInvoking] = useState(false);
  const [result, setResult] = useState<McpInvokeResult | null>(null);
  const [invokeError, setInvokeError] = useState<string | null>(null);

  const loadServers = useCallback(async () => {
    setServersLoading(true);
    setServersError(null);
    try {
      setServers(await fetchMcpServers());
    } catch (err) {
      setServersError(err instanceof Error ? err.message : String(err));
    } finally {
      setServersLoading(false);
    }
  }, []);

  const loadTools = useCallback(async (name: string) => {
    setToolsLoading(true);
    setToolsError(null);
    setTools([]);
    try {
      const data = await fetchMcpTools(name);
      setTools(data.tools);
    } catch (err) {
      setToolsError(err instanceof Error ? err.message : String(err));
    } finally {
      setToolsLoading(false);
    }
  }, []);

  const selectServer = useCallback(
    (name: string | null) => {
      setServer(name);
      setResult(null);
      setInvokeError(null);
      if (name) void loadTools(name);
      else setTools([]);
    },
    [loadTools]
  );

  const invoke = useCallback(
    async (tool: string, args: Record<string, unknown>) => {
      if (!server) return null;
      setInvoking(true);
      setInvokeError(null);
      setResult(null);
      try {
        const res = await invokeMcpTool(server, tool, args);
        setResult(res);
        return res;
      } catch (err) {
        setInvokeError(err instanceof Error ? err.message : String(err));
        return null;
      } finally {
        setInvoking(false);
      }
    },
    [server]
  );

  const clearResult = useCallback(() => {
    setResult(null);
    setInvokeError(null);
  }, []);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  return {
    servers,
    serversLoading,
    serversError,
    reloadServers: loadServers,
    server,
    selectServer,
    tools,
    toolsLoading,
    toolsError,
    reloadTools: () => (server ? loadTools(server) : undefined),
    invoking,
    result,
    invokeError,
    invoke,
    clearResult,
  };
}
