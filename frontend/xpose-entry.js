/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side entry view
 */

import { encodeURIqs, addElement, addJButton, addText, toggle_display, deleteConfirm, noopAlert, AjaxError } from './utils.js'

export default class entryView {

  constructor () {
    this.toplevel = document.createElement('div')
    const menu = addElement(this.toplevel,'div')
    { // return button
      const button = addJButton(menu,'arrowreturnthick-1-w',{title:'Return to listing view'})
      button.addEventListener('click',()=>this.close().catch(err=>this.onerror(err)))
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh entry'})
      button.addEventListener('click',()=>this.refresh().catch(err=>this.onerror(err)))
    }
    { // save entry button
      const button = this.el_save = addJButton(menu,'arrowthickstop-1-n',{title:'Save entry'})
      button.addEventListener('click',()=>this.save().catch(err=>this.onerror(err)))
    }
    { // delete entry button
      const button = addJButton(menu,'trash',{title:'Delete entry (if confirmed)',class:'caution'})
      button.addEventListener('click',()=>this.remove().catch(err=>this.onerror(err)))
    }
    { // go-to "attachment" button
      const button = addJButton(menu,'folder-open',{title:'Show attachment'})
      button.addEventListener('click',()=>this.go_attach().catch(err=>this.onerror(err)))
    }
    { // toggle access editor button
      const button = addJButton(menu,'unlocked',{title:'Toggle access controls editor'})
      button.addEventListener('click',()=>toggle_display(this.accessEditor.element))
      this.el_locked = button
    }
    { // info box (short name of entry)
      addText(menu)
      const span = this.el_short = addElement(menu,'span')
    }
    { // access editor form
      const div = addElement(this.toplevel,'div')
      this.accessEditor = new JSONEditor(div,this.accessEditorConfig())
      this.accessEditor.on('change',()=>{if(this.active)this.set_dirty(true)})
    }
    { // main entry editor form
      this.el_main = addElement(this.toplevel,'div')
    }
    this.entry = null
    this.editor = null
    this.active = false
  }

  async display_new (cat) {
    this.display({ cat: cat, value: {}, short: `New ${cat}` })
  }
  async display_old (oid) {
    const sql = 'SELECT oid,version,cat,short,value as "value [JSON]",attach,access FROM EntryShort WHERE oid=:oid'
    const resp = await axios({url:encodeURIqs(`${this.url}/main`,{sql:sql,oid:oid}),headers:{'Cache-Control':'no-store'}}).
      catch(err=>{throw new AjaxError(err)})
    this.display(resp.data[0])
  }

  display (entry) {
    this.set_dirty(!('oid' in entry))
    this.entry = entry
    this.accessEditor.element.style.display = 'none'
    this.active = false
    this.accessEditor.setValue(entry.access)
    this.editor = new JSONEditor(this.el_main,this.editorConfig())
    this.editor.on('ready',()=>{ this.setShort(); this.setLocked(); this.show() })
    this.editor.on('change',()=>{ if (this.active) {this.set_dirty(true)} else {this.active=true} })
  }

  async save () {
    if (!this.get_dirty()) { return noopAlert() }
    const errors = this.editor.validate()
    if (errors.length) { return this.error('validation',errors) }
    this.entry.value = this.editor.getValue()
    this.entry.access = this.accessEditor.getValue()||null
    this.editor.disable()
    const resp = await axios({url:`${this.url}/main`,method:'PUT',data:this.entry}).
      finally(()=>this.editor.enable()).
      catch(err=>{throw new AjaxError(err)})
    this.set_dirty(false)
    for (const att of ['oid','version','short','attach']) { this.entry[att] = resp.data[att] }
    this.setShort()
    this.setLocked()
  }

  async remove () {
    if (!deleteConfirm()) return
    this.editor.disable()
    await axios({url:`${this.url}/main`,method:'DELETE',data:{oid:this.entry.oid}}).
      catch(err=>{throw new AjaxError(err)})
    await this.close(true)
  }

  async refresh () {
    if (!this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      const oid = this.entry.oid
      if (!oid) { await this.display_new(this.entry.cat) }
      else { await this.display_old(oid) }
    }
  }

  async close (force) {
    if (force || !this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      await this.views.listing.display()
    }
  }

  async go_attach () {
    if (!this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      await this.views.attach.display_entry(this.entry)
    }
  }

  setShort () { this.el_short.innerText = this.entry.short; this.el_short.title = `:${this.entry.oid}` }
  setLocked () { this.el_locked.firstElementChild.className = this.entry.access?'ui-icon ui-icon-locked':'ui-icon ui-icon-unlocked' }

  show_dirty (flag) { this.el_save.style.backgroundColor = flag?'red':'' }

  editorConfig () {
    return {
      ajax: true,
      schema: { $ref: `${this.dataUrl}/cats/${this.entry.cat}/schema.json` },
      startval: this.entry.value,
      display_required_only: true,
      remove_empty_properties: true,
      disable_array_delete_all_rows: true,
      disable_array_delete_last_row: true,
      remove_button_labels: true,
      array_controls_top: true,
      show_opt_in: true
    }
  }

  accessEditorConfig () {
    return {
      schema: { title: 'Access editor', type: 'string', options: { inputAttributes: { size: 160 } } },
      startval: null,
      remove_button_labels: true
    }
  }
}
