const allowedPaths=new Set(['/','/decisions','/assistant','/assistant-feedback','/notification-settings']);
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function notificationRoute(data,authenticated){
  if(!authenticated||!data||typeof data!=='object'||typeof data.path!=='string'||!allowedPaths.has(data.path))return null;
  if(data.path==='/assistant'){
    if(data.event_type!=='assistant_response_ready'||typeof data.conversation_id!=='string'||!uuid.test(data.conversation_id))return null;
    return {pathname:'/assistant',params:{conversationId:data.conversation_id}};
  }
  return data.path;
}
