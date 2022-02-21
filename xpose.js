/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: a JSON database manager (client side)
 */

//
// Xpose
//

class Xpose {
  constructor () {
    this.url = {main:'main.cgi.py',attach:'mainAttach.cgi.py',cats:'cats/.visible.json',jschema:(cat)=>{return `cats/jschemas/${cat}.json`}}
    this.views = {}
    this.current = null
    this.dirty = false
    this.addView('console',new consoleView())
    this.addView('listing',new listingView())
    this.addView('entry',new entryView())
    this.addView('attach',new attachView())
    this.el_view = document.getElementById('xpose-view')
    this.el_progress = document.getElementById('xpose-progress')
  }
  addView (name,view) {
    view.error = (label,x) => this.error(`${name}:${label}`,x)
    view.ajaxError = (err) => this.ajaxError(err)
    view.progressor = (label) => this.progressor(`${name}:${label}`)
    view.set_dirty = (flag) => { this.dirty = flag; view.show_dirty(flag); }
    view.get_dirty = () => { return this.dirty }
    view.confirm_dirty = () => { return this.dirty && !unsavedConfirm() }
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
    this.el_view.innerHTML = view.name
    this.current.toplevel.style.display = ''
  }

  progressor (label) {
    // displays a progress bar and returns an object with the following fields:
    //   update: an update callback to pass to the target task (argument: percent_complete)
    //   close: a close callback (no argument)
    const div = document.createElement('div')
    div.innerHTML = `<progress max="1." value="0."></progress><button type="button"><span class="ui-icon ui-icon-closethick"></span></button> <strong>${label}</strong>`
    const el = div.firstElementChild
    let cancelled = false
    el.nextElementSibling.addEventListener('click',()=>{cancelled=true},false)
    this.el_progress.appendChild(div)
    return {
      update:(percent)=>{el.value=percent.toFixed(3);return cancelled},
      close:()=>{this.el_progress.removeChild(div)}
    }
  }
  ajaxError (err) {
    let errText = null
    if (err.response) { errText = `Server error ${err.response.status} ${err.response.statusText}\n${err.response.data}` }
    else if (err.request) { errText = `No response received from Server\n${err.request}` }
    else { errText = err.message}
    this.error('ajax',errText)
  }
  error (label,x) { this.views.console.display(this.current,`ERROR: ${label}\n${x===null?'':x}`) }
}

//
// listingView
//

class listingView {

  constructor () {
    this.el_main = document.getElementById('listing')
    this.el_updater = document.getElementById('listing-query')
    this.el_new = document.getElementById('listing-new')
    this.el_editor = document.getElementById('listing-editor')
    this.el_count = document.getElementById('listing-count')
    const query = `SELECT oid,Short.value as short
FROM Entry LEFT JOIN Short ON Short.entry=oid
-- WHERE created LIKE '2013-%'
ORDER BY created DESC
LIMIT 30`
    this.editor = new JSONEditor(
      this.el_editor,
      {
        schema: { title: 'Query editor', type: 'string', format: 'textarea', default: query, options: { inputAttributes: { rows: 5, cols: 160 } } },
        remove_button_labels: true,
      }
    ).on('ready',()=>{
      setTimeout(()=>{this.editor.on('change',()=>{this.set_dirty(true)})},100) // timeout needed
    })
    this.toplevel = this.el_main.parentNode
  }

  display () {
    if (this.el_new.children.length==0) {
      axios({url:this.url.cats,headers:{'Cache-Control':'no-store'}}).
        then((resp)=>{this.setupNew(resp.data)}).
        catch(this.ajaxError)
    }
    this.editor.disable()
    axios({url:`${this.url.main}?sql=${encodeURIComponent(this.editor.getValue())}`,headers:{'Cache-Control':'no-store'}}).
      finally(()=>this.editor.enable()).
      then((resp)=>this.display1(resp.data)).
      catch(this.ajaxError)
  }

  display1 (data) {
    this.set_dirty(false)
    this.el_count.innerHTML = String(data.length)
    this.el_main.innerHTML = ''
    for (const entry of data) {
      const tr = this.el_main.insertRow()
      tr.addEventListener('click',()=>{this.go_entry_old(entry.oid)},false)
      tr.insertCell().innerHTML = entry.short
    }
    this.el_editor.style.display = 'none'
    this.show()
  }

  setupNew (cats) {
    for (const cat of cats) {
      const span = document.createElement('span')
      span.innerHTML = cat
      span.addEventListener('click',(e)=>{this.go_entry_new(cat)},false)
      this.el_new.appendChild(span)
    }
  }

  go_entry_new (cat) { if (!this.confirm_dirty()) this.views.entry.display_new(cat) }
  go_entry_old (oid) { if (!this.confirm_dirty()) this.views.entry.display_old(oid) }

  show_dirty (flag) { this.el_updater.style.backgroundColor = flag?'red':'' }

}

//
// entryView
//

class entryView {

  constructor () {
    this.el_main = document.getElementById('entry')
    this.el_updater = document.getElementById('entry-save')
    this.el_delete = document.getElementById('entry-delete')
    this.el_attach = document.getElementById('entry-attach')
    this.el_short = document.getElementById('entry-short')
    this.entry = null
    this.editor = null
    this.toplevel = this.el_main.parentNode
  }

  display_new (cat) {
    this.display({ cat: cat, value: {}, short: `New ${cat}` })
  }
  display_old (oid) {
    axios({url:`${this.url.main}?oid=${encodeURIComponent(oid)}`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display(resp.data)).
      catch(this.ajaxError)
  }

  display (entry) {
    this.set_dirty(!('oid' in entry))
    this.entry = entry
    this.editor = new JSONEditor(
      this.el_main,
      {
        ajax: true,
        schema: { $ref: this.url.jschema(entry.cat) },
        display_required_only: true,
        remove_empty_properties: true,
        disable_array_delete_all_rows: true,
        disable_array_delete_last_row: true,
        remove_button_labels: true,
        array_controls_top: true,
        show_opt_in: true
      }
    ).on('ready',()=>{
      this.editor.setValue(entry.value)
      setTimeout(()=>{this.editor.on('change',()=>{this.set_dirty(true)})},100) // timeout needed
      this.setShort()
      this.show()
    })
  }

  save () {
    if (!this.get_dirty()) { return noopAlert() }
    const errors = this.editor.validate()
    if (errors.length) { return this.error('validation',errors) }
    this.entry.value = this.editor.getValue()
    this.editor.disable()
    axios({url:this.url.main,method:'PUT',data:this.entry}).
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
  }

  remove () {
    if (!deleteConfirm()) return
    this.editor.disable()
    axios({url:this.url.main,method:'DELETE',data:{oid:this.entry.oid}}).
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

  setShort () { this.el_short.innerHTML = this.entry.short; this.el_short.title = this.entry.oid }

  show_dirty (flag) { this.el_updater.style.backgroundColor = flag?'red':'' }
}

//
// attachView
//

class attachView {

  constructor () {
    this.el_main = document.getElementById('attach')
    this.el_short = document.getElementById('attach-short')
    this.el_path = document.getElementById('attach-path')
    this.el_updater = document.getElementById('attach-save')
    this.el_upload = document.getElementById('attach-upload')
    this.chunk = 1
    this.entry = null
    this.path = null
    this.version = null
    this.inputs = null
    this.toplevel = this.el_main.parentNode
  }

  display_entry (entry) {
    this.entry = entry
    this.el_short.innerHTML = entry.short
    this.display(entry.attach)
  }

  display_clean(path) { if (!this.confirm_dirty()) this.display(path) }

  display(path) {
    axios({url:`${this.url.attach}?path=${encodeURIComponent(path)}`,headers:{'Cache-Control':'no-store'}}).
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
      upload({file:file,url:this.url.attach,chunk:this.chunk,progress:progressor.update}).
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
    axios({url:this.url.attach,method:'PATCH',data:{ops:ops,path:this.path,version:this.version}}).
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
      const a = document.createElement('a')
      a.title = p
      a.href = 'javascript:'
      a.innerHTML = name
      a.addEventListener('click',()=>this.display_clean(p),false)
      this.el_path.appendChild(a)
      const span = document.createElement('span')
      span.innerHTML = '/'
      this.el_path.appendChild(span)
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
    const pname = new_name?'New file':name
    const rname = new_name||name
    tr.insertCell().innerHTML = mtime
    if (size<0) {
      tr.insertCell().innerHTML = `${-size} item${size==-1?'':'s'}`
      const cell = tr.insertCell()
      cell.innerHTML = `<a href="javascript:">${pname}</a>`
      cell.firstElementChild.addEventListener('click',()=>this.display_clean(`${this.path}/${name}`),false)
    }
    else {
      tr.insertCell().innerHTML = human_size(size)
      tr.insertCell().innerHTML = `<a target="_blank" href="attach/${this.path}/${rname}">${pname}</a>`
    }
    const inp = document.createElement('input')
    this.inputs.push([name,inp,new_name!==null])
    tr.insertCell().appendChild(inp)
    inp.size = '50'
    inp.value = rname
    inp.addEventListener('input',()=>{this.set_dirty(true)},false)
  }

  show_dirty (flag) { this.el_updater.style.backgroundColor = flag?'red':'' }
}

//
// consoleView
//

class consoleView {
  constructor () {
    this.el_main = document.getElementById('console')
    this.origin = null
    this.toplevel = this.el_main.parentNode
  }
  display (origin,msg) {
    this.origin = origin
    this.el_main.innerHTML = msg
    this.show()
  }
  close () {
    this.origin.show()
  }
}

//
// Main call
//

xpose = null
window.onload = function () {
  xpose = new Xpose()
  window.addEventListener('beforeunload',function (e) { if (xpose.dirty) {e.preventDefault();e.returnValue=''} },false)
  xpose.views.listing.display()
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

function toggle_display (el) { el.style.display = (el.style.display?'':'none') }
function unsavedConfirm () { return window.confirm('Unsaved changes will be lost. Are you sure you want to proceed ?') }
function deleteConfirm () { return window.confirm('Are you sure you want to delete this entry ?') }
function noopAlert () { window.alert('Nothing to save !') }
