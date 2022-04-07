/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side listing view
 */

import { addElement, addJButton, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert } from './utils.js'

export default class listingView {

  constructor () {
    this.toplevel = document.createElement('table')
    const thead = addElement(this.toplevel,'thead')
    const menu = thead.insertRow().insertCell()
    { // refresh button
      const button = this.el_refresh = addJButton(menu,'refresh',{title:'Refresh listing'})
      button.addEventListener('click',()=>{this.display()})
    }
    { // go-to "new entry" form
      const button = addJButton(menu,'plusthick',{title:'Create a new entry'})
      const select = this.el_new = addElement(menu,'select',{style:'display:none;position:absolute;z-index:1;'})
      button.addEventListener('click',()=>{select.style.display='';select.selectedIndex=-1;select.focus()})
      select.addEventListener('blur',()=>{select.style.display='none'})
    }
    { // toggle query editor button
      const button = addJButton(menu,'help',{title:'Toggle query editor'})
      button.addEventListener('click',()=>{toggle_display(this.editor.element)})
    }
    { // go-to "manage" button
      const button = addJButton(menu,'wrench',{title:'Manage xpose instance'})
      button.addEventListener('click',()=>{this.go_manage()})
    }
    { // info box (number of entries)
      addText(menu)
      const span = this.el_count = addElement(menu,'span')
      addText(menu,' entries')
    }
    { // query editor
      const div = addElement(thead.insertRow().insertCell(),'div',{style:'display:none'})
      this.editor = new JSONEditor(div,this.editorConfig())
    }
    { // listing table
      this.el_main = addElement(this.toplevel,'tbody',{class:'listing'})
    }
    this.active = false
    this.editor.on('change',()=>{if (this.active) {this.set_dirty(true)} else {this.active=true} })
  }

  display () {
    this.editor.disable()
    axios({url:`${this.url}/main?sql=${encodeURIComponent(this.editor.getValue())}`,headers:{'Cache-Control':'no-store'}}).
      finally(()=>this.editor.enable()).
      then((resp)=>this.display1(resp.data)).
      catch(this.ajaxError)
  }

  display1 (data) {
    this.set_dirty(false)
    this.el_count.innerText = String(data.length)
    this.el_main.innerHTML = ''
    for (const entry of data) {
      const tr = this.el_main.insertRow()
      tr.addEventListener('click',()=>{this.go_entry_old(entry.oid)})
      tr.title = String(entry.oid)
      const access = entry.access?'visible':'hidden'
      tr.insertCell().innerHTML = `<span style="visibility:${access}; font-size:x-small;">🔒</span>${entry.short}`
    }
    this.editor.element.style.display = 'none'
    this.show()
  }

  setupNew (cats) {
    this.el_new.size = cats.length
    for (const cat of cats) {
      const o = addElement(this.el_new,'option',{style:'color:black;background-color:white;'})
      o.innerText = cat
      o.addEventListener('mouseenter',()=>{o.style.filter='invert(100%)'})
      o.addEventListener('mouseleave',()=>{o.style.filter='invert(0%)'})
      o.addEventListener('click',()=>{this.go_entry_new(cat)})
    }
  }

  go_manage () { if (!this.confirm_dirty()) this.views.manage.display() }

  go_entry_new (cat) { if (!this.confirm_dirty()) this.views.entry.display_new(cat) }
  go_entry_old (oid) { if (!this.confirm_dirty()) this.views.entry.display_old(oid) }

  show_dirty (flag) { this.el_refresh.style.backgroundColor = flag?'red':'' }

  editorConfig () {
    const queryDefault = `SELECT oid,access,Short.value as short
FROM Entry LEFT JOIN Short ON Short.entry=oid
-- WHERE created LIKE '2013-%'
ORDER BY created DESC
LIMIT 30`
    return {
      schema: { title: 'Query editor', type: 'string', format: 'textarea', options: { inputAttributes: { rows: 5, cols: 160 } } },
      startval: queryDefault
    }
  }
}
