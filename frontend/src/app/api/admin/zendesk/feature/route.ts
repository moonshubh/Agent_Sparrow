import { 
  validateAdminAccess, 
  getAdminConfig, 
  callUpstream 
} from '../_shared/route-helpers';

export async function POST(request: Request) {
  const authError = await validateAdminAccess();
  if (authError) {
    return authError;
  }

  const configResult = getAdminConfig();
  if (configResult instanceof Response) {
    return configResult;
  }

  const body = await request.text();
  return callUpstream(
    '/api/v1/integrations/zendesk/feature',
    configResult,
    {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}
