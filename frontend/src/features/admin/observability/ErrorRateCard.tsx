// Error Rate Card Component
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertTriangle, CheckCircle } from "lucide-react";

interface ErrorRateCardProps {
  totalRequests?: number;
  errorCount?: number;
  errorRate?: number;
  errorsByType?: Record<string, number>;
}

export function ErrorRateCard({
  totalRequests = 0,
  errorCount = 0,
  errorRate = 0,
  errorsByType = {},
}: ErrorRateCardProps) {
  const isErrorRateHigh = errorRate > 5;
  
  return (
    <Card className={isErrorRateHigh ? "border-red-200" : ""}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Error Rate</CardTitle>
        {isErrorRateHigh ? (
          <AlertTriangle className="h-4 w-4 text-red-600" />
        ) : (
          <CheckCircle className="h-4 w-4 text-green-600" />
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-bold">
              {errorRate.toFixed(2)}%
            </span>
            <span className="text-sm text-muted-foreground">
              {errorCount}/{totalRequests.toLocaleString()} requests
            </span>
          </div>
          
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${
                isErrorRateHigh ? "bg-red-600" : "bg-green-600"
              }`}
              style={{ width: `${Math.min(errorRate, 100)}%` }}
            />
          </div>
        </div>
        
        {Object.keys(errorsByType).length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">
              Errors by Type
            </p>
            <div className="space-y-1">
              {Object.entries(errorsByType).map(([type, count]) => (
                <div 
                  key={type}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-muted-foreground">{type}</span>
                  <span className="font-medium">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        
        <div className="text-xs text-muted-foreground">
          <p>Target: &lt; 5% error rate</p>
        </div>
      </CardContent>
    </Card>
  );
}
