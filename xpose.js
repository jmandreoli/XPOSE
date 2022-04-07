/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: a JSON database manager (client side)
 */

//
// Xpose
//

class Xpose {
  constructor (url,views) {
    this.url = url
    this.current = null
    this.dirty = false
    this.variant = (document.cookie.split('; ').find(row=>row.startsWith('xpose-variant='))||'').substr(14)
    views = views||{}
    const default_views = { console:consoleView, listing:listingView, entry:entryView, attach:attachView, manage:manageView }
    for (const [name,default_factory] of Object.entries(default_views)) { this.addView(name,new (views[name]||default_factory)()) }
    window.addEventListener('beforeunload',(e)=>{ if (this.dirty) {e.preventDefault();e.returnValue=''} })
  }
  addView (name,view) {
    view.error = (label,x) => this.error(`${name}:${label}`,x)
    view.ajaxError = (err) => this.ajaxError(err)
    view.progressor = (label) => this.progressor(`${name}:${label}`)
    view.variant = this.variant
    view.toggle_variant = () => this.toggle_variant()
    view.set_dirty = (flag) => { this.dirty = flag; view.show_dirty(flag); }
    view.get_dirty = () => this.dirty
    view.confirm_dirty = () => this.dirty && !unsavedConfirm()
    view.show = () => this.show(view)
    view.url = this.url
    view.views = this.views
    view.name = name
    this.views[name] = view
    view.toplevel.style.display = 'none'
  }
  show (view) {
    if (this.current===view) return
    if (this.current!==null) { this.current.toplevel.style.display = 'none' }
    this.current = view
    this.el_view.innerText = view.name
    this.current.toplevel.style.display = ''
  }

  progressor (label) {
    // displays a progress bar and returns an object with the following fields:
    //   update: an update callback to pass to the target task (argument: percent_complete)
    //   close: a close callback (no argument)
    const div = addElement(this.el_progress,'div')
    const el = addElement(div,'progress',{max:'1.',value:'0.',})
    const button = addJButton(div,'closethick',{title:'Interrupt upload'})
    addText(div,label)
    let cancelled = false
    button.addEventListener('click',()=>{cancelled=true})
    return {
      update:(percent)=>{el.value=percent.toFixed(3);return cancelled},
      close:()=>{this.el_progress.removeChild(div)}
    }
  }
  ajaxError (err) {
    let errText = null
    if (err.response) { errText = `Server error ${err.response.status} ${err.response.statusText}\n${err.response.data}` }
    else if (err.request) { errText = `No response received from Server\n${err.request.url}` }
    else { errText = err.message}
    this.error('ajax',errText)
  }
  error (label,x) { this.views.console.display(this.current,`ERROR: ${label}\n${x===null?'':x}`) }
  toggle_variant () { document.cookie=`xpose-variant=${this.variant?'':'shadow'}`;window.location.reload() }
  render() {
    {
      this.el_progress = addElement(document.body,'div',{class:'xpose-progress',style:'display:none'})
    }
    {
      const h1 = addElement(document.body,'h1')
      addText(h1,'Xpose: ')
      this.el_view = addElement(h1,'span')
    }
    {
      if (this.variant) {
        const warning = addElement(document.body,'div',{class:'xpose-variant-warning'})
        addText(warning,this.variant)
        addJButton(warning,'close').addEventListener('click',()=>this.toggle_variant())
      }
    }
    for (const view of Object.values(this.views)) { document.body.appendChild(view.toplevel) }
    this.views.listing.display()
  }
}

//
// listingView
//

class listingView {

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
    axios({url:`${this.url.xpose}/main?sql=${encodeURIComponent(this.editor.getValue())}`,headers:{'Cache-Control':'no-store'}}).
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

//
// entryView
//

class entryView {

  constructor () {
    this.toplevel = document.createElement('div')
    const menu = addElement(this.toplevel,'div')
    { // return button
      const button = addJButton(menu,'arrowreturnthick-1-w',{title:'Return to listing view'})
      button.addEventListener('click',()=>{this.close()})
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh entry'})
      button.addEventListener('click',()=>{this.refresh()})
    }
    { // save entry button
      const button = this.el_save = addJButton(menu,'arrowthickstop-1-n',{title:'Save entry'})
      button.addEventListener('click',()=>{this.save()})
    }
    { // delete entry button
      const button = addJButton(menu,'trash',{title:'Delete entry (if confirmed)',class:'caution'})
      button.addEventListener('click',()=>{this.remove()})
    }
    { // go-to "attachment" button
      const button = addJButton(menu,'folder-open',{title:'Show attachment'})
      button.addEventListener('click',()=>{this.go_attach()})
    }
    { // toggle access editor button
      const button = addJButton(menu,'unlocked',{title:'Toggle access controls editor'})
      button.addEventListener('click',()=>{toggle_display(this.accessEditor.element)})
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

  display_new (cat) {
    this.display({ cat: cat, value: {}, short: `New ${cat}` })
  }
  display_old (oid) {
    axios({url:`${this.url.xpose}/main?oid=${encodeURIComponent(oid)}`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display(resp.data)).
      catch(this.ajaxError)
  }

  display (entry) {
    this.set_dirty(!('oid' in entry))
    this.entry = entry
    this.accessEditor.element.style.display = 'none'
    this.active = false
    this.accessEditor.setValue(entry.access)
    this.editor = new JSONEditor(this.el_main,this.editorConfig())
    this.editor.on('ready',()=>{ this.setShort(); this.setLocked(); this.show() })
    this.editor.on('change',()=>{if (this.active) {this.set_dirty(true)} else {this.active=true} })
  }

  save () {
    if (!this.get_dirty()) { return noopAlert() }
    const errors = this.editor.validate()
    if (errors.length) { return this.error('validation',errors) }
    this.entry.value = this.editor.getValue()
    this.entry.access = this.accessEditor.getValue()||null
    this.editor.disable()
    axios({url:`${this.url.xpose}/main`,method:'PUT',data:this.entry}).
      finally(()=>this.editor.enable()).
      then((resp)=>this.save1(resp.data)).
      catch(this.ajaxError)
  }
  save1 (data) {
    this.set_dirty(false)
    this.entry.oid = data.oid
    this.entry.version = data.version
    this.entry.short = data.short
    this.entry.attach = data.attach
    this.setShort()
    this.setLocked()
  }

  remove () {
    if (!deleteConfirm()) return
    this.editor.disable()
    axios({url:`${this.url.xpose}/main`,method:'DELETE',data:{oid:this.entry.oid}}).
      then((resp)=>this.close(true)).
      catch(this.ajaxError)
  }

  refresh () {
    if (!this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      const oid = this.entry.oid
      if (!oid) { this.display_new(this.entry.cat) }
      else { this.display_old(oid) }
    }
  }

  close (force) {
    if (force || !this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      this.views.listing.display()
    }
  }

  go_attach () {
    if (!this.confirm_dirty()) {
      this.editor.destroy()
      this.el_main.innerHTML = ''
      this.views.attach.display_entry(this.entry)
    }
  }

  setShort () { this.el_short.innerText = this.entry.short; this.el_short.title = this.entry.oid }
  setLocked () { this.el_locked.firstElementChild.className = this.entry.access?'ui-icon ui-icon-locked':'ui-icon ui-icon-unlocked' }

  show_dirty (flag) { this.el_save.style.backgroundColor = flag?'red':'' }

  editorConfig () {
    return {
      ajax: true,
      schema: { $ref: this.url.jschema(this.entry.cat) },
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

//
// attachView
//

class attachView {

  constructor () {
    this.toplevel = document.createElement('table')
    const thead = addElement(this.toplevel,'thead')
    const menu = thead.insertRow().insertCell()
    { // return button
      const button = addJButton(menu,'arrowreturnthick-1-w',{title:'Return to entry view'})
      button.addEventListener('click',()=>{this.close()})
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh attachment'})
      button.addEventListener('click',()=>{this.refresh()})
    }
    { // upload form
      const button = addJButton(menu,'plusthick',{title:'Upload a new attachment'})
      const input = addElement(menu,'input',{'type':'file','multiple':'multiple','style':'display:none'})
      button.addEventListener('click',()=>{input.click()})
      input.addEventListener('change',()=>{this.upload(input.files)})
    }
    { // save button
      const button = addJButton(menu,'arrowthickstop-1-n',{title:'Save attachment'})
      button.addEventListener('click',()=>{this.save()})
      this.el_save = button
    }
    { // infobox (entry short name and path)
      addText(menu)
      this.el_short = addElement(menu,'span')
      addText(menu)
      this.el_path = addElement(menu,'span')
    }
    { // listing table
      this.el_main = addElement(this.toplevel,'tbody',{class:'attach'})
    }
    this.chunk = 1
    this.entry = null
    this.path = null
    this.version = null
    this.inputs = null
  }

  display_entry (entry) {
    this.entry = entry
    this.el_short.innerText = entry.short
    this.display(entry.attach)
  }

  display_clean(path) { if (!this.confirm_dirty()) this.display(path) }

  display(path) {
    axios({url:`${this.url.xpose}/attach?path=${encodeURIComponent(path)}`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display1(path,resp.data)).
      catch(this.ajaxError)
  }

  display1 (path,data) {
    this.version = data.version
    this.set_dirty(false)
    this.setPath(path)
    this.el_main.innerHTML = ''
    this.inputs = []
    for (const [name,mtime,size] of data.content) {this.addRow(name,mtime,size,null)}
    this.show()
  }

  upload (files) {
    for (const file of files) {
      const progressor = this.progressor(file.name)
      upload({file:file,url:`${this.url.xpose}/attach`,chunk:this.chunk,progress:progressor.update}).
        then((result)=>{progressor.close();this.addRow(result.name,result.mtime,file.size,file.name)}).
        catch((err)=>{progressor.close();this.error('upload',err)})
    }
  }

  save () {
    const ops = []
    for (const [name,inp,is_new] of this.inputs) {
      const iname = inp.value.trim()
      if (is_new || iname!=name) { ops.push({src:name,trg:iname,is_new:is_new}) }
    }
    if (!ops.length) return noopAlert()
    axios({url:`${this.url.xpose}/attach`,method:'PATCH',data:{ops:ops,path:this.path,version:this.version}}).
      then((resp)=>this.save1(resp.data)).
      catch(this.ajaxError)
  }
  save1 (data) {
    if (data.errors.length) { this.error('save',data.errors.join('\n')); delete data.errors; }
    else { this.display1(this.path,data) }
  }

  refresh () { this.display_clean(this.path) }

  close () {
    if (!this.confirm_dirty()) {
      this.el_main.innerHTML = ''
      this.views.entry.display(this.entry)
    }
  }

  setPath (path) {
    const path_level = (p,name) => {
      const a = addElement(this.el_path,'a',{title:p,href:'javascript:'})
      a.innerText = name
      a.addEventListener('click',()=>this.display_clean(p))
      addText(this.el_path,'/')
    }
    this.path = path
    this.el_path.innerHTML = ''
    const comp = path.split('/')
    let p = `${comp[0]}/${comp[1]}`
    path_level(p,'•')
    for (let i=2;i<comp.length;i++) { p = `${p}/${comp[i]}`; path_level(p,comp[i]) }
  }

  addRow (name,mtime,size,new_name) {
    if (new_name) {this.set_dirty(true)}
    const tr = this.el_main.insertRow()
    tr.insertCell().innerText = mtime
    if (size<0) {
      tr.insertCell().innerText = `${-size} item${size==-1?'':'s'}`
      const cell = tr.insertCell()
      cell.innerHTML = `<a href="javascript:">${name}</a>`
      cell.firstElementChild.addEventListener('click',()=>this.display_clean(`${this.path}/${name}`))
    }
    else {
      tr.insertCell().innerText = human_size(size)
      tr.insertCell().innerHTML = `<a target="_blank" href="${this.url.attach}/${new_name?'.uploaded':this.path}/${name}">${new_name?'New file':name}</a>`
    }
    const inp = addElement(tr.insertCell(),'input',{size:'50',value:new_name||name})
    inp.addEventListener('input',()=>{this.set_dirty(true)})
    this.inputs.push([name,inp,new_name!==null])
  }

  show_dirty (flag) { this.el_save.style.backgroundColor = flag?'red':'' }
}

//
// manageView
//

class manageView {

  constructor () {
    this.toplevel = document.createElement('div')
    const menu = addElement(this.toplevel,'div')
    { // return button
      const button = addJButton(menu,'arrowreturnthick-1-w',{title:'Return to listing view'})
      button.addEventListener('click',()=>{this.close()})
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh view'})
      button.addEventListener('click',()=>{this.display()})
    }
    { // shadow button
      const button = this.el_shadow = addJButton(menu,'newwin',{title:'Transfer instance->shadow'})
      button.addEventListener('click',()=>{this.shadow()})
    }
    { // infobox
      addText(menu,' Current version: ')
      this.el_version = addElement(menu,'span')
    }
    {
      const div = addElement(this.toplevel,'div')
      this.el_stats = {}
      const table = addElement(div,'table',{class:'manage-stats'})
      const thead = addElement(table,'thead')
      const td = thead.insertRow().insertCell()
      td.colSpan = '2'; td.innerText = 'Statistics'
      const tbody = addElement(table,'tbody')
      {
        const tr = tbody.insertRow()
        tr.insertCell().innerText = 'cats'
        this.el_stats.cat = addElement(tr.insertCell(),'table')
      }
      {
        const tr = tbody.insertRow()
        tr.insertCell().innerText = 'access'
        this.el_stats.access = addElement(tr.insertCell(),'table')
      }
    }
  }

  display () {
    axios({url:`${this.url.xpose}/manage`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display1(resp.data)).
      catch(this.ajaxError)
  }

  display1 (data) {
    if (this.variant) { this.el_shadow.title = 'Transfer shadow->instance'; this.el_shadow.className = 'caution' } // done once never changed
    this.el_version.innerText = `${data.version}[${new Date(data.ts*1000).toISOString()}]`
    const stats = data.stats
    const el_cat = this.el_stats.cat
    el_cat.innerHTML = ''
    for (const [cat,cnt] of Object.entries(stats.cat)) {
      const tr = el_cat.insertRow()
      addText(tr.insertCell(),cat)
      addText(tr.insertCell(),String(cnt))
    }
    const el_access = this.el_stats.access
    el_access.innerHTML = ''
    for (const [access,cnt] of Object.entries(stats.access)) {
      const tr = el_access.insertRow()
      addText(tr.insertCell(),access)
      addText(tr.insertCell(),String(cnt))
    }
    this.show()
  }

  shadow () {
    if (this.variant && !window.confirm('You are about to override the entire Xpose instance.')) { return }
    axios({url:`${this.url.xpose}/manage`,method:'POST'}).then(()=>this.toggle_variant()).catch(this.ajaxError)
  }

  close () { this.views.listing.display() }
}

//
// consoleView
//

class consoleView {
  constructor () {
    this.toplevel = document.createElement('div')
    this.el_main = addElement(this.toplevel,'textarea',{class:'console caution'})
    {
      const button = addJButton(this.toplevel,'arrowreturnthick-1-w',{class:'caution'})
      button.addEventListener('click',()=>{this.close()})
    }
    this.origin = null
  }
  display (origin,msg) {
    this.origin = origin
    this.el_main.value = msg
    this.show()
  }
  close () {
    this.origin.show()
  }
}

//
// Utilities
//

async function upload(x) {
  // x: object with the following fields
  //   file: a File or Blob object
  //   url: must support POST with blob content and optional target in query string (generated by the server if not provided)
  //   chunk (default 1): int, in MiB
  //   target (optional): target file name
  //   progress (optional): progress callback with one input (percent_complete)
  // Sends the file (method POST) by chunks to the given url assumed to return a result object for each chunk
  // A result object describes the uploaded file after each chunk transfer with 3 fields:
  //   name (invariable), mtime (last modification time), size (in bytes)
  // Returns (a promise on) the last result object
  const file = x.file, url = x.url, progress = x.progress, chunk = (x.chunk||1)*0x100000
  const req = {method:'POST',headers:{'Content-Type':'application/octet-stream'}}, size = file.size
  let target = x.target||'', position = 0, nextPosition = 0, result = null, ongoing = true
  if (progress) {
    const controller = new AbortController()
    req.signal = controller.signal
    req.onUploadProgress = (evt)=>{if(progress((position+evt.loaded)/size)){controller.abort()}}
  }
  while(ongoing) {
    nextPosition = position+chunk
    if (nextPosition>=size) { nextPosition = size; ongoing=false; }
    req.url = `${url}?target=${target}`
    req.data = await file.slice(position,nextPosition).arrayBuffer()
    const resp = await axios(req)
    result = resp.data
    target = result.name // in case it was not specified in the input
    position = nextPosition
  }
  return result
}

function human_size (size) {
  // size: int (number of bytes)
  // returns a human readable string representing size
  const thr = 1024.
  const units = ['K','M','G','T','P','E','Z']
  if (size<thr) return `${size}B`
  size /= thr
  for (const u of units) {
    if (size<thr) return `${size.toFixed(2)}${u}iB`
    size /= thr
  }
  return `${size}YiB` // :-)
}

// short-hands

function addElement(container,tag,attrs) {
	const el = document.createElement(tag)
	if (attrs) { for (const [k,v] of Object.entries(attrs)) {el.setAttribute(k,v)} }
	container.appendChild(el)
	return el
}
function addJButton(container,icon,attrs) {
  const button = addElement(container,'button',attrs)
  addElement(button,'span',{class:`ui-icon ui-icon-${icon}`})
  return button
}
function addText(container,data) {
  const text = document.createTextNode(data||' ')
  container.appendChild(text)
}
function toggle_display (el) { el.style.display = (el.style.display?'':'none') }
function unsavedConfirm () { return window.confirm('Unsaved changes will be lost. Are you sure you want to proceed ?') }
function deleteConfirm () { return window.confirm('Are you sure you want to delete this entry ?') }
function noopAlert () { window.alert('Nothing to save !') }
