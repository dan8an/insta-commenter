import {describe,it,expect} from 'vitest';
import {validUrl} from './api';
describe('URL validation',()=>{it.each(['https://instagram.com/p/abc/','https://www.instagram.com/reel/a_1/?x=y'])('accepts %s',u=>expect(validUrl(u)).toBe(true));it.each(['https://instagram.com.evil/p/a/','https://evil@instagram.com/p/a/','javascript:alert(1)','https://instagram.com/stories/a/','invalid'])('rejects %s',u=>expect(validUrl(u)).toBe(false))});
