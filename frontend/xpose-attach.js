/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side attach view
 */

import { upload, human_size, addElement, addJButton, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert } from './utils.js'

export default class attachView {

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
    axios({url:`${this.url}/attach?path=${encodeURIComponent(path)}`,headers:{'Cache-Control':'no-store'}}).
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
      upload({file:file,url:`${this.url}/attach`,chunk:this.chunk,progress:progressor.update}).
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
    axios({url:`${this.url}/attach`,method:'PATCH',data:{ops:ops,path:this.path,version:this.version}}).
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
      tr.insertCell().innerHTML = `<a target="_blank" href="${this.dataUrl}/attach/${new_name?'.uploaded':this.path}/${name}">${new_name?'New file':name}</a>`
    }
    const inp = addElement(tr.insertCell(),'input',{size:'50',value:new_name||name})
    inp.addEventListener('input',()=>{this.set_dirty(true)})
    this.inputs.push([name,inp,new_name!==null])
  }

  show_dirty (flag) { this.el_save.style.backgroundColor = flag?'red':'' }
}
