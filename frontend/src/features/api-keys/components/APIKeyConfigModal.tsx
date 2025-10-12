'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/shared/ui/dialog';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Label } from '@/shared/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert';
import { Badge } from '@/shared/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { Separator } from '@/shared/ui/separator';
import { ScrollArea } from '@/shared/ui/scroll-area';
import {
  Key,
  CheckCircle,
  XCircle,
  RefreshCw,
  Eye,
  EyeOff,
  Trash2,
  Save,
  TestTube,
  Shield
} from 'lucide-react';
import {
  getUserAPIKeys,
  testAPIKeyConnectivityWithKey as testAPIKeyConnectivity,
  validateAPIKeyFormat,
  APIKeyType,
  UserAPIKeyMasked,
  configureAPIKey,
  deleteAPIKey,
} from '@/services/api/endpoints/api-key-service-secure';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { toast } from 'sonner';
import { cn } from '@/shared/lib/utils';

interface APIKeyConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface APIKeyFormData {
  type: APIKeyType;
  apiKey: string;
  isVisible: boolean;
}

const API_KEY_INFO = {
  [APIKeyType.GEMINI]: {
    label: 'Gemini API Key',
    description: 'Powers primary AI agent capabilities',
    placeholder: 'AIza...',
    helpUrl: 'https://makersuite.google.com/app/apikey',
    color: 'blue'
  },
  [APIKeyType.OPENAI]: {
    label: 'OpenAI API Key',
    description: 'Enables OpenAI provider in chat',
    placeholder: 'sk-...',
    helpUrl: 'https://platform.openai.com/api-keys',
    color: 'purple'
  },
  [APIKeyType.TAVILY]: {
    label: 'Tavily API Key',
    description: 'Enables web search and research features',
    placeholder: 'tvly-...',
    helpUrl: 'https://tavily.com/api',
    color: 'green'
  },
  [APIKeyType.FIRECRAWL]: {
    label: 'Firecrawl API Key',
    description: 'Web scraping and content extraction',
    placeholder: 'fc_...',
    helpUrl: 'https://firecrawl.dev/dashboard',
    color: 'orange'
  }
};

export const APIKeyConfigModal: React.FC<APIKeyConfigModalProps> = ({
  isOpen,
  onClose
}) => {
  const [activeTab, setActiveTab] = useState<APIKeyType>(APIKeyType.GEMINI);
  const [formData, setFormData] = useState<Record<APIKeyType, APIKeyFormData>>({
    [APIKeyType.GEMINI]: { type: APIKeyType.GEMINI, apiKey: '', isVisible: false },
    [APIKeyType.OPENAI]: { type: APIKeyType.OPENAI, apiKey: '', isVisible: false },
    [APIKeyType.TAVILY]: { type: APIKeyType.TAVILY, apiKey: '', isVisible: false },
    [APIKeyType.FIRECRAWL]: { type: APIKeyType.FIRECRAWL, apiKey: '', isVisible: false }
  });
  const [existingKeys, setExistingKeys] = useState<UserAPIKeyMasked[]>([]);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState<APIKeyType | null>(null);
  const [testResults, setTestResults] = useState<Record<APIKeyType, { success: boolean; message: string } | null>>({
    [APIKeyType.GEMINI]: null,
    [APIKeyType.OPENAI]: null,
    [APIKeyType.TAVILY]: null,
    [APIKeyType.FIRECRAWL]: null
  });
  const { session } = useAuth();

  const fetchExistingKeys = useCallback(async () => {
    if (!session?.access_token) return;

    try {
      setLoading(true);
      const keys = await getUserAPIKeys(session.access_token);
      setExistingKeys(keys);
    } catch (error) {
      console.error('Failed to fetch existing API keys:', error)
      toast.error('Failed to fetch existing API keys');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token]);

  useEffect(() => {
    if (isOpen) {
      void fetchExistingKeys();
    }
  }, [isOpen, fetchExistingKeys]);

  const handleInputChange = (type: APIKeyType, value: string) => {
    setFormData(prev => ({
      ...prev,
      [type]: { ...prev[type], apiKey: value }
    }));
    
    // Clear test result when input changes
    setTestResults(prev => ({ ...prev, [type]: null }));
  };

  const toggleVisibility = (type: APIKeyType) => {
    setFormData(prev => ({
      ...prev,
      [type]: { ...prev[type], isVisible: !prev[type].isVisible }
    }));
  };

  const handleTest = async (type: APIKeyType) => {
    if (!session?.access_token || !formData[type].apiKey) {
      toast.error('Please enter an API key to test');
      return;
    }

    // Validate format first
    if (!validateAPIKeyFormat(type, formData[type].apiKey)) {
      setTestResults(prev => ({
        ...prev,
        [type]: { success: false, message: 'Invalid API key format' }
      }));
      return;
    }

    try {
      setTesting(type);
      const result = await testAPIKeyConnectivity(
        session.access_token,
        type,
        formData[type].apiKey
      );
      
      setTestResults(prev => ({
        ...prev,
        [type]: result
      }));
      
      if (result.success) {
        toast.success(`${API_KEY_INFO[type].label} is valid and working!`);
      } else {
        toast.error(`${API_KEY_INFO[type].label} test failed: ${result.message}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection test failed';
      setTestResults(prev => ({
        ...prev,
        [type]: { success: false, message }
      }));
      toast.error(message);
    } finally {
      setTesting(null);
    }
  };

  const handleSave = async (type: APIKeyType) => {
    if (!session?.access_token || !formData[type].apiKey) {
      toast.error('Please enter an API key to save');
      return;
    }

    // Validate format
    if (!validateAPIKeyFormat(type, formData[type].apiKey)) {
      toast.error('Invalid API key format');
      return;
    }

    try {
      setLoading(true);
      
      const result = await configureAPIKey(session.access_token, type, formData[type].apiKey);

      if (!result.success) {
        throw new Error(result.message || 'Failed to save API key');
      }

      toast.success(result.message || `${API_KEY_INFO[type].label} saved successfully!`);
      
      // Clear form data for this key
      setFormData(prev => ({
        ...prev,
        [type]: { ...prev[type], apiKey: '', isVisible: false }
      }));
      
      // Refresh existing keys
      await fetchExistingKeys();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save API key');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (type: APIKeyType) => {
    if (!session?.access_token) return;

    const confirmed = window.confirm(`Are you sure you want to delete your ${API_KEY_INFO[type].label}?`);
    if (!confirmed) return;

    try {
      setLoading(true);
      
      const result = await deleteAPIKey(session.access_token, type);

      if (!result.success) {
        throw new Error(result.message || 'Failed to delete API key');
      }

      toast.success(result.message || `${API_KEY_INFO[type].label} deleted successfully`);
      
      await fetchExistingKeys();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete API key');
    } finally {
      setLoading(false);
    }
  };

  const renderKeyStatus = (type: APIKeyType) => {
    const existingKey = existingKeys.find(k => k.api_key_type === type);
    const testResult = testResults[type];

    if (testResult) {
      return (
        <Alert className={cn(
          "glass-effect",
          testResult.success ? "border-green-500/50" : "border-destructive/50"
        )}>
          <AlertTitle className="flex items-center gap-2">
            {testResult.success ? (
              <CheckCircle className="h-4 w-4 text-green-500" />
            ) : (
              <XCircle className="h-4 w-4 text-destructive" />
            )}
            Test Result
          </AlertTitle>
          <AlertDescription>{testResult.message}</AlertDescription>
        </Alert>
      );
    }

    if (existingKey) {
      return (
        <Card className="glass-effect">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Current Key</CardTitle>
              <Badge variant={existingKey.is_active ? "default" : "secondary"}>
                {existingKey.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <code className="text-xs bg-secondary/50 px-2 py-1 rounded">
                {existingKey.masked_key}
              </code>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleDelete(type)}
                disabled={loading}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      );
    }

    return null;
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl glass-effect backdrop-blur-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-accent" />
            API Key Configuration
          </DialogTitle>
          <DialogDescription>
            Manage your API keys for different services. These keys enable various AI features.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as APIKeyType)}>
          <TabsList className="grid w-full grid-cols-3 glass-effect">
            {Object.values(APIKeyType).map(type => (
              <TabsTrigger key={type} value={type} className="data-[state=active]:glass-effect">
                <div className="flex items-center gap-1.5">
                  <Key className="h-3 w-3" />
                  <span className="text-xs">{type}</span>
                </div>
              </TabsTrigger>
            ))}
          </TabsList>

          <ScrollArea className="h-[400px] mt-4">
            {Object.values(APIKeyType).map(type => (
              <TabsContent key={type} value={type} className="space-y-4">
                <Card className="glass-effect">
                  <CardHeader>
                    <CardTitle className="text-lg">{API_KEY_INFO[type].label}</CardTitle>
                    <CardDescription>{API_KEY_INFO[type].description}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {renderKeyStatus(type)}

                    <Separator />

                    <div className="space-y-2">
                      <Label htmlFor={`api-key-${type}`}>
                        {existingKeys.find(k => k.api_key_type === type) ? 'Replace with New Key' : 'Enter API Key'}
                      </Label>
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Input
                            id={`api-key-${type}`}
                            type={formData[type].isVisible ? 'text' : 'password'}
                            placeholder={API_KEY_INFO[type].placeholder}
                            value={formData[type].apiKey}
                            onChange={(e) => handleInputChange(type, e.target.value)}
                            disabled={loading}
                            className="pr-10 glass-input"
                          />
                          <button
                            type="button"
                            onClick={() => toggleVisibility(type)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-secondary/20 rounded"
                          >
                            {formData[type].isVisible ? (
                              <EyeOff className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <Eye className="h-4 w-4 text-muted-foreground" />
                            )}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleTest(type)}
                        disabled={!formData[type].apiKey || loading || testing === type}
                        className="glass-effect"
                      >
                        {testing === type ? (
                          <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                        ) : (
                          <TestTube className="h-3 w-3 mr-1" />
                        )}
                        Test Connection
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleSave(type)}
                        disabled={!formData[type].apiKey || loading}
                        className="glass-effect"
                      >
                        <Save className="h-3 w-3 mr-1" />
                        Save Key
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        asChild
                      >
                        <a href={API_KEY_INFO[type].helpUrl} target="_blank" rel="noopener noreferrer">
                          Get API Key
                        </a>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            ))}
          </ScrollArea>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
