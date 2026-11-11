// Verify incremental rendering and name suggestions without personal data.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.value='';this.classList={toggle(){}};this.parent=null}
 append(...nodes){for(const node of nodes){if(node.parent)node.parent.children.splice(node.parent.children.indexOf(node),1);this.children.push(node);node.parent=this}}
 replaceChildren(...nodes){this.replaced=(this.replaced||0)+1;this.children=[];this.append(...nodes)}
 insertBefore(node,next){if(node.parent)node.parent.children.splice(node.parent.children.indexOf(node),1);const index=this.children.indexOf(next);this.children.splice(index<0?this.children.length:index,0,node);node.parent=this}
 setAttribute(name,value){this[name]=value}
 remove(){if(this.parent)this.parent.children.splice(this.parent.children.indexOf(this),1)}
}
const elements=new Map();
for(const id of ['status','undo','sort','search','groups','selection','knownNames','namesHint','merge','clear','target','mergedName','mergeSummary','mergeDialog','confirmMerge','photoTitle','photoGrid','photoDialog'])elements.set('#'+id,new Element('div'));
elements.get('#sort').value='largest';
let data={groups:[{id:1,name:'Example',count:8,folder:'Example - Pessoa_0001'},{id:2,name:'',count:3,folder:'Pessoa_0002'}],can_undo:false};
const context={console,Date,Set,Map,document:{querySelector:id=>elements.get(id),querySelectorAll:()=>[],createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})},fetch:async()=>({ok:true,json:async()=>structuredClone(data)})};
vm.createContext(context);
const source=fs.readFileSync('manage_face_groups.py','utf8').split('<script>')[1].split('</script>')[0];
vm.runInContext(source,context);
(async()=>{
 await new Promise(resolve=>setImmediate(resolve));
 const container=elements.get('#groups'),first=container.children[0],second=container.children[1];
 const input=second.children.find(node=>node.tag==='input');input.value='Unsaved draft';
 assert.equal(elements.get('#knownNames').children[0].value,'Example');
 data.groups[0].name='Updated';data.groups[0].folder='Updated - Pessoa_0001';
 await vm.runInContext('load(1)',context);
 assert.equal(container.children[0],first);assert.equal(container.children[1],second);
 assert.equal(input.value,'Unsaved draft');assert.equal(container.replaced,undefined);
 assert.equal(first.children.find(node=>node.tag==='input').value,'Updated');
 assert.equal(elements.get('#knownNames').children[0].value,'Updated');
 const image=first.children[0],imageURL=image.src;
 second.children[1].children[0].checked=true;second.children[1].children[0].onchange();
 assert.equal(container.children[0],first);assert.equal(image.src,imageURL);
 assert.equal(input.value,'Unsaved draft');
 console.log('Name suggestions, stable cards, draft preservation and checkbox selection passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
