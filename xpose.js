//
// Xpose
//

class Xpose {
  constructor () {
    this.url = 'main.cgi.py'
    this.urla = 'mainAttach.cgi.py'
    this.urlc = (cat) => {return `cats/jschemas/${cat}.json`}
    this.views = {}
    this.current = null
    this.addView('console',new consoleView())
    this.addView('listing',new listingView())
    this.addView('entry',new entryView())
    this.addView('attach',new attachView())
    this.el_view = document.getElementById('xpose-view')
    this.el_new = document.getElementById('xpose-new')
    this.el_progress = document.getElementById('xpose-progress')
    var setupNew = (cats) => {
      this.el_new.size = 1+cats.length
      var options = []
      cats.forEach((cat) => { options.push(`<option>${cat}</option>`) })
      this.el_new.innerHTML += options.join('')
    }
    jQuery.ajax({ url:'cats/.visible.json',cache:false,success:setupNew,error:this.ajaxError })
  }
  addView (name,view) {
    view.error = (label,x) => this.error(`${name}.${label}`,x)
    view.ajaxError = this.ajaxError
    view.progressor = this.progressor
    view.show = () => this.show(view)
    view.url = this.url; view.urla = this.urla; view.urlc = this.urlc
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
  progressor = (label) => {
    var div = document.createElement('div')
    div.innerHTML = `<progress max="1." value="0."></progress><button type="button"><span class="ui-icon ui-icon-closethick"></span></button> loading: <strong>${label}</strong>`
    div.style.border = 'thin solid red'
    var el = div.firstElementChild
    var cancelled=false
    el.nextElementSibling.addEventListener('click',()=>{cancelled=true},false)
    this.el_progress.appendChild(div)
    return {
      update:(percent)=>{el.value=percent.toFixed(3);if(cancelled){this.el_progress.removeChild(div)};return cancelled},
      close:()=>{this.el_progress.removeChild(div)}
    }
  }
  ajaxError = (jqxhr,textStatus,errorThrown) => { this.error('ajax',`${errorThrown}\n${jqxhr.responseText}`) }
  error = (label,x) => { this.views.console.display(this.current,`ERROR: ${label}\n${x===null?'':x}`) }
}

//
// listingView
//

class listingView {

  constructor () {
    this.el_main = document.getElementById('listing')
    this.el_updater = document.getElementById('listing-query')
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
    this.editor.disable()
    jQuery.ajax({
      url:this.url, data:{sql:this.editor.getValue()}, cache:false,
      success:(data)=>this.display1(data),
      error:this.ajaxError
    }).always(()=>this.editor.enable())
  }

  display1 (data) {
    this.set_dirty(false)
    this.el_count.innerHTML = String(data.length)
    this.el_main.innerHTML = ''
    data.forEach((entry) => {
      var tr = this.el_main.insertRow()
      tr.addEventListener('click',()=>{this.views.entry.display_old(entry.oid)},false)
      tr.insertCell().innerHTML = entry.short
    })
    this.el_editor.style.display = 'none'
    this.show()
  }

  set_dirty (flag) {
    this.dirty = flag
    this.el_updater.style.backgroundColor = flag?'red':''
  }

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
    this.dirty = null
    this.toplevel = this.el_main.parentNode
  }

  display_new (cat) {
    this.display({ cat: cat, value: {}, short: `New ${cat}` })
  }
  display_old (oid) {
    jQuery.ajax({
      url:this.url, data:{oid:oid}, cache:false,
      success:(data)=>this.display(data),
      error:this.ajaxError
    })
  }

  display (entry) {
    this.set_dirty(!('oid' in entry))
    this.entry = entry
    this.editor = new JSONEditor(
      this.el_main,
      {
        ajax: true,
        schema: { $ref: this.urlc(entry.cat) },
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
      this.el_short.innerHTML = short(this.entry)
      this.show()
    })
  }

  save () {
    if (!this.dirty) return noopAlert()
    var errors = this.editor.validate()
    if (errors.length) { return this.error('validation',errors) }
    this.entry.value = this.editor.getValue()
    this.editor.disable()
    return jQuery.ajax({
      url:this.url, method:'PUT', data:JSON.stringify(this.entry), contentType:'text/json',processData:false,
      success:(data)=>{this.save1(data)},
      error:this.ajaxError
    }).always(()=>{this.editor.enable()})
  }
  save1 (data) {
    this.set_dirty(false)
    this.entry.oid = data.oid
    this.entry.version = data.version
    this.entry.short = data.short
    this.entry.attach = data.attach
    this.el_short.innerHTML = short(this.entry)
  }

  remove () {
    if (!deleteConfirm()) return
    this.editor.disable()
    jQuery.ajax({
      url:this.url, method:'DELETE', data:{oid:this.entry.oid},
      success:()=>{this.close(true)},
      error:this.ajaxError
    })
  }

  refresh () {
    if (this.dirty && !unsavedConfirm()) return
    var oid = this.entry.oid
    var cat = this.entry.cat
    this.editor.destroy()
    this.el_main.innerHTML = ''
    if (typeof oid == 'undefined') { this.display_new(cat) }
    else { this.display_old(oid) }
  }

  close (force) {
    if (!force && this.dirty && !unsavedConfirm()) return
    this.editor.destroy()
    this.el_main.innerHTML = ''
    this.views.listing.display()
  }

  set_dirty (flag) {
    this.dirty = flag
    this.el_updater.style.backgroundColor = flag?'red':''
  }
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
    this.el_uplevel = document.getElementById('attach-uplevel')
    this.entry = null
    this.path = null
    this.version = null
    this.inputs = null
    this.dirty = null
    this.toplevel = this.el_main.parentNode
  }

  display (path) {
    this.entry = this.views.entry.entry
    if (path===null) {
      path = this.entry.attach
      if (this.views.entry.dirty && !unsavedConfirm()) return
    }
    this.el_short.innerHTML = this.entry.short
    jQuery.ajax({
      url:this.urla,data:{path:path},
      success: (data)=>{this.display1(path,data)},
      error: this.ajaxError
    })
  }

  display1 (path,data) {
    this.path = path
    this.version = data.version
    this.el_path.innerHTML = path
    this.el_uplevel.style.display = data.toplevel?'none':''
    this.set_dirty(false)
    this.el_main.innerHTML = ''
    this.inputs = []
    data.content.forEach(([name,mtime,size])=>{this.addRow(name,mtime,size,null)})
    this.show()
  }

  upload (files) {
    files.forEach((file)=>{
      var progressor = this.progressor(file.name)
      upload({
        file:file,url:this.urla,chunk:1,progress:progressor.update,
        success: (target,mtime) => {progressor.close();this.addRow(target,mtime,file.size,file.name)},
        error: (err) => {progressor.close();this.error(err)}
      })
    })
  }

  save () {
    var ops = []
    this.inputs.forEach(([name,inp,is_new])=>{
      var iname = inp.value.trim()
      if (is_new || iname!=name) { ops.push({src:name,trg:iname,is_new:is_new}) }
    })
    if (!ops.length) return noopAlert()
    jQuery.ajax({
      url:this.urla,method:'PUT',data:JSON.stringify({ops:ops,path:this.path,version:this.version}),contentType:'text/json',processData:false,
      success: (data)=>{this.save1(data)},
      error: this.ajaxError
    })
  }
  save1 (data) {
    if (data.errors.length) { this.error('save',data.errors.join('\n')); delete data.errors; }
    else { this.display1(this.path,data) }
  }

  refresh () {
    if (this.dirty && !unsavedConfirm()) return
    this.display(this.path)
  }

  uplevel () {
    var path = this.path.split('/')
    path.pop()
    if (path.length>=2 && (!this.dirty || unsavedConfirm())) { this.display(path.join('/')) }
  }

  close () {
    if (this.dirty && !unsavedConfirm()) return
    this.el_main.innerHTML = ''
    this.views.entry.show()
  }

  addRow (name,mtime,size,new_name) {
    if (new_name) {this.set_dirty(true)}
    var tr = this.el_main.insertRow()
    var td = tr.insertCell()
    if (size<0) { // directory
      var span = document.createElement('span')
      td.appendChild(span)
      span.className = 'ui-icon ui-icon-folder-open'
      span.addEventListener('click',()=>{this.display(`${this.path}/${name}`)},false)
    }
    var pname = new_name?'New file':name
    var rname = new_name||name
    tr.insertCell().innerHTML = mtime
    tr.insertCell().innerHTML = size<0?`${-size} item${size==-1?'':'(s)'}`:format_size(size)
    tr.insertCell().innerHTML = size<0?pname:`<a target="_blank" href="attach/${this.path}/${rname}">${pname}</a>`
    var inp = document.createElement('input')
    this.inputs.push([name,inp,new_name!==null])
    tr.insertCell().appendChild(inp)
    inp.size = '50'
    inp.value = rname
    inp.addEventListener('change',()=>{this.set_dirty(true)},false)
  }

  set_dirty (flag) {
    this.dirty = flag
    this.el_updater.style.backgroundColor = flag?'red':''
  }
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
// Uploader
//

function upload (req) {
  // expected fields in req:
  // file: a File or Blob object
  // url protocol: must support POST with blob content and target in query string
  // success(name,mtime),failure(err),progress(percentcomplete): callbacks
  // chunk: int, in MiB
  var target = ''
  var position = 0
  var nextPosition = 0
  var size = req.file.size
  var chunk = (req.chunk||1)*0x100000
  var progress = req.progress
  var xhr = ()=>{return new window.XMLHttpRequest()}
  if (progress) {
    xhr = ()=>{
      var x = new window.XMLHttpRequest()
      x.upload.addEventListener('progress',(evt)=>{if(progress((position+evt.loaded)/size)){console.log('abort',position,size);x.abort()}},false)
      return x;
    }
  }
  var upload1 = () => {
    nextPosition = Math.min(position+chunk,size)
    var reader = new FileReader()
    reader.onload = ()=>{jQuery.ajax({
      url:`${req.url}?target=${target}`,method:'POST',xhr:xhr,
      data:reader.result,contentType:'application/octet-stream',processData:false,
      success: (data)=>{upload2(data)},
      error: req.failure
    })}
    reader.readAsArrayBuffer(req.file.slice(position,nextPosition))
  }
  var upload2 = (data) => {
    target = data.name; position = nextPosition
    if (position<size) { upload1() }
    else { req.success(target,data.mtime) }
  }
  upload1()
}

//
// Main call
//

xpose = null
window.onload = function () {
  JSONEditor.defaults.options.theme = 'bootstrap4'
  JSONEditor.defaults.options.iconlib = 'jqueryui'
  xpose = new Xpose()
  xpose.views.listing.display()
}

// Utilities

toggle_display = function (el) { el.style.display = (el.style.display?'':'none') }
short = function (entry) { return `[${entry.oid}] ${entry.short}` }
format_size = function (size) {
  var thr = 1024.
  if (size<thr) return `${size}B`
  size /= thr
  var units = ['K','M','G','T','P','E','Z']
  for (var i=0;i<units.length;i++){
    if (size<thr) return `${size.toFixed(2)}${units[i]}iB`
    size /= thr
  }
  return `${size}YiB` // :-)
}
unsavedConfirm = ()=>{return window.confirm('Unsaved changes will be lost. Are you sure you want to proceed ?')}
deleteConfirm = ()=>{return window.confirm('Are you sure you want to delete this entry ?')}
noopAlert = ()=>{window.alert('Nothing to save !')}
