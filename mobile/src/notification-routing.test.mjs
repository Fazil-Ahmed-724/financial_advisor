import test from 'node:test';
import assert from 'node:assert/strict';
import {notificationRoute} from './notification-routing.js';
const id='11111111-1111-4111-8111-111111111111';
test('assistant notification opens its conversation when authenticated',()=>assert.deepEqual(notificationRoute({path:'/assistant',event_type:'assistant_response_ready',conversation_id:id},true),{pathname:'/assistant',params:{conversationId:id}}));
test('authentication is required',()=>assert.equal(notificationRoute({path:'/assistant',event_type:'assistant_response_ready',conversation_id:id},false),null));
test('rejects missing IDs and unsupported paths',()=>{assert.equal(notificationRoute({path:'/assistant',event_type:'assistant_response_ready'},true),null);assert.equal(notificationRoute({path:'/trade',conversation_id:id},true),null)});
test('non-assistant allowlisted routes remain bounded',()=>assert.equal(notificationRoute({path:'/assistant-feedback',event_type:'feedback_review_status_changed'},true),'/assistant-feedback'));
test('generic test notification opens settings when authenticated',()=>assert.equal(notificationRoute({path:'/notification-settings',event_type:'test_notification'},true),'/notification-settings'));
