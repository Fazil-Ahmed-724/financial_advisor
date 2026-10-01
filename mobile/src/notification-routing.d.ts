export type NotificationRoute='/'|'/decisions'|'/assistant-feedback'|{pathname:'/assistant';params:{conversationId:string}};
export function notificationRoute(data:unknown,authenticated:boolean):NotificationRoute|null;
