// Langfuse Link Component
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface LangfuseLinkProps {
  environment?: string;
}

export function LangfuseLink({ environment = "development" }: LangfuseLinkProps) {
  const baseUrl = "https://cloud.langfuse.com";
  
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ExternalLink className="h-5 w-5" />
          Langfuse Dashboard
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          View detailed traces, metrics, and analytics in the Langfuse dashboard.
        </p>
        
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Environment:</span>
            <span className="font-medium capitalize">{environment}</span>
          </div>
          
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => window.open(baseUrl, '_blank')}
          >
            <ExternalLink className="mr-2 h-4 w-4" />
            Open Langfuse Dashboard
          </Button>
        </div>
        
        <div className="text-xs text-muted-foreground">
          <p>Note: You need appropriate permissions to view project data.</p>
        </div>
      </CardContent>
    </Card>
  );
}
