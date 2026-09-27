import {test} from 'node:test'
import assert from 'node:assert/strict'
import {api} from './api.js'

test('interrupted login retries once',async()=>{
 let calls=0;globalThis.fetch=async()=>{if(++calls===1)throw new TypeError('Load failed');return new Response(JSON.stringify({id:'test'}))}
 assert.equal((await api('/auth/login','POST',{})).id,'test');assert.equal(calls,2)
})
test('invalid credentials never retry',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({detail:'Email or password is incorrect.'}),{status:401})}
 await assert.rejects(api('/auth/login','POST',{}),/incorrect/);assert.equal(calls,1)
})
test('payments and other writes never retry',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;throw new TypeError('Load failed')}
 await assert.rejects(api('/billing/checkout','POST',{}),/Connection interrupted/);assert.equal(calls,1)
})
test('persistent read failure is bounded',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;throw new TypeError('Load failed')}
 await assert.rejects(api('/me'),/Connection interrupted/);assert.equal(calls,2)
})
