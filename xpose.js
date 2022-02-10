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
    view.ajaxError = (j,t,e) => this.ajaxError(j,t,e)
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
    var div = document.createElement('div')
    div.innerHTML = `<progress max="1." value="0."></progress><button type="button"><span class="ui-icon ui-icon-closethick"></span></button> <strong>${label}</strong>`
    var el = div.firstElementChild
    var cancelled = false
    el.nextElementSibling.addEventListener('click',()=>{cancelled=true},false)
    this.el_progress.appendChild(div)
    return {
      update:(percent)=>{el.value=percent.toFixed(3);if(cancelled){this.el_progress.removeChild(div)};return cancelled},
      close:()=>{this.el_progress.removeChild(div)}
    }
  }
  ajaxError (jqxhr,textStatus,errorThrown) { this.error('ajax',`${errorThrown}\n${jqxhr.responseText}`) }
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
    var query = `SELECT oid,Short.value as short
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
    if (this.el_new.rows.length==0) {
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
      var tr = this.el_main.insertRow()
      tr.addEventListener('click',()=>{this.go_entry_old(entry.oid)},false)
      tr.insertCell().innerHTML = entry.short
    }
    this.el_editor.style.display = 'none'
    this.show()
  }

  setupNew (cats) {
    for (const cat of cats) {
      var td = this.el_new.insertRow().insertCell()
      td.innerHTML = cat
      td.addEventListener('click',(e)=>{this.go_entry_new(cat)},false)
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
    var errors = this.editor.validate()
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
      var oid = this.entry.oid
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
    this.path = path
    this.version = data.version
    this.set_dirty(false)
    this.el_main.innerHTML = ''
    this.setPath(path)
    this.inputs = []
    for (const [name,mtime,size] of data.content) {this.addRow(name,mtime,size,null)}
    this.show()
  }

  upload (files) {
    for (const file of files) {
      var progressor = this.progressor(file.name)
      upload({
        file:file,url:this.url.attach,chunk:this.chunk,progress:progressor.update,
        success: (target,mtime) => {progressor.close();this.addRow(target,mtime,file.size,file.name)},
        error: (err) => {progressor.close();this.error(err)}
      })
    }
  }

  save () {
    var ops = []
    for (const [name,inp,is_new] of this.inputs) {
      var iname = inp.value.trim()
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
    var path_level = (p,name) => {
      var a = document.createElement('a')
      a.href = 'javascript:'
      a.innerHTML = name
      a.addEventListener('click',()=>this.display_clean(p),false)
      this.el_path.appendChild(a)
      var span = document.createElement('span')
      span.innerHTML = '/'
      this.el_path.appendChild(span)
      return a
    }
    this.el_path.innerHTML = ''
    var path = this.path.split('/')
    var p = `${path[0]}/${path[1]}`
    path_level(p,'•').title = p
    for (var i=2;i<path.length;i++) { p = `${p}/${path[i]}`; path_level(p,path[i]) }
  }

  addRow (name,mtime,size,new_name) {
    if (new_name) {this.set_dirty(true)}
    var tr = this.el_main.insertRow()
    var pname = new_name?'New file':name
    var rname = new_name||name
    tr.insertCell().innerHTML = mtime
    if (size<0) {
      tr.insertCell().innerHTML = `${-size} item${size==-1?'':'s'}`
      var cell = tr.insertCell()
      cell.innerHTML = `<a href="javascript:">${pname}</a>`
      cell.firstElementChild.addEventListener('click',()=>this.display_clean(`${this.path}/${name}`),false)
    }
    else {
      tr.insertCell().innerHTML = human_size(size)
      tr.insertCell().innerHTML = `<a target="_blank" href="attach/${this.path}/${rname}">${pname}</a>`
    }
    var inp = document.createElement('input')
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

function upload (req) {
  // req: object with the following fields
  //   file: a File or Blob object
  //   url: must support POST with blob content and target in query string
  //   success(name,mtime),failure(err),progress(percentcomplete): callbacks
  //   chunk: int, in MiB
  // Sends the file (method POST) to the given url
  // The success callback is passed the file name and last modification time
  var target = ''
  var position = 0
  var nextPosition = 0
  var size = req.file.size
  var chunk = (req.chunk||1)*0x100000
  var progress = req.progress
  var controller = progress?new AbortController():null
  var upload1 = () => {
    nextPosition = Math.min(position+chunk,size)
    var reader = new FileReader()
    req1 = {url:`${req.url}?target=${target}`,method:'POST',headers:{'Content-Type':'application/octet-stream'}}
    if (controller) {
      req1.signal = controller.signal
      req1.onUploadProgress = (evt)=>{if(progress((position+evt.loaded)/size)){console.log('abort',position,size);controller.abort()}}
    }
    reader.onload = ()=>{
      req1.data = reader.result
      axios(req1).then((resp)=>upload2(resp.data)).catch(req.failure)
    }
    reader.readAsArrayBuffer(req.file.slice(position,nextPosition))
  }
  var upload2 = (data) => {
    target = data.name; position = nextPosition
    if (position<size) { upload1() }
    else { req.success(target,data.mtime) }
  }
  upload1()
}

function human_size (size) {
  // size: int (number of bytes)
  // returns a human readable string representing size
  var thr = 1024.
  if (size<thr) return `${size}B`
  size /= thr
  var units = ['K','M','G','T','P','E','Z']
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
