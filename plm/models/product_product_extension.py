# -*- encoding: utf-8 -*-
##############################################################################
#
#    OmniaSolutions, Your own solutions
#    Copyright (C) 2010 OmniaSolutions (<http://omniasolutions.eu>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging
from datetime import datetime
from openerp import models
from openerp import fields
from openerp import api
from openerp import _
from openerp.exceptions import ValidationError
from openerp.exceptions import UserError
from openerp import osv
import openerp.tools as tools

_logger = logging.getLogger(__name__)

USED_STATES = [('draft', _('Draft')),
               ('confirmed', _('Confirmed')),
               ('released', _('Released')),
               ('undermodify', _('UnderModify')),
               ('obsoleted', _('Obsoleted'))]
USEDIC_STATES = dict(USED_STATES)


class plm_component(models.Model):
    _inherit = 'product.product'

    linkeddocuments = fields.Many2many('plm.document',
                                       'plm_component_document_rel',
                                       'component_id',
                                       'document_id',
                                       _('Linked Docs'))
    tmp_material = fields.Many2one('plm.material',
                                   _('Raw Material'),
                                   required=False,
                                   change_default=True,
                                   help=_("Select raw material for current product"))
    tmp_surface = fields.Many2one('plm.finishing',
                                  _('Surface Finishing'),
                                  required=False,
                                  change_default=True,
                                  help=_("Select surface finishing for current product"))
    father_part_ids = fields.Many2many('product.product',
                                       compute=_father_part_compute,
                                       string=_("BoM Hierarchy"),
                                       store=False)
    create_date = fields.Datetime(_('Date Created'),
                                  readonly=True)
    write_date = fields.Datetime(_('Date Modified'),
                                 readonly=True)
    std_description = fields.Many2one('plm.description',
                                      _('Standard Description'),
                                      required=False,
                                      change_default=True,
                                      default=False,
                                      help=_("Select standard description for current product."))
    std_umc1 = fields.Char(_('UM / Feature 1'),
                           size=32,
                           default='',
                           help=_("Allow to specifiy a unit measure for the first feature."))
    std_value1 = fields.Float(_('Value 1'),
                              default=0,
                              help=_("Assign value to the first characteristic."))
    std_umc2 = fields.Char(_('UM / Feature 2'),
                           size=32,
                           default='',
                           help=_("Allow to specifiy a unit measure for the second feature."))
    std_value2 = fields.Float(_('Value 2'),
                              default=0,
                              help=_("Assign value to the second characteristic."))
    std_umc3 = fields.Char(_('UM / Feature 3'),
                           size=32,
                           default='',
                           help=_("Allow to specifiy a unit measure for the third feature."))
    std_value3 = fields.Float(_('Value 3'),
                              default=0,
                              help=_("Assign value to the second characteristic."))

    # Don't overload std_umc1, std_umc2, std_umc3 setting them related to std_description because odoo try to set value
    # of related fields and integration users doesn't have write permissions in std_description. The result is that
    # integration users can't create products if in changed values there is std_description

    @api.onchange('std_description')
    def on_change_stddesc(self):
        if self.std_description:
            if self.std_description.description:
                self.description = self.std_description.description
                if self.std_description.umc1:
                    self.std_umc1 = self.std_description.umc1
                if self.std_description.umc2:
                    self.std_umc2 = self.std_description.umc2
                if self.std_description.umc3:
                    self.std_umc3 = self.std_description.umc3
                if self.std_description.unitab:
                    self.description = self.description + " " + self.std_description.unitab

    @api.onchange('std_value1', 'std_value2', 'std_value3')
    def on_change_stdvalue(self):
        if self.std_description:
            if self.std_description.description:
                self.description = self.computeDescription(self.std_description, self.std_description.description, self.std_umc1, self.std_umc2, self.std_umc3, self.std_value1, self.std_value2, self.std_value3)

    @api.onchange('name')
    def on_change_name(self):
        if self.name:
            results = self.search([('name', '=', self.name)])
            if len(results) > 0:
                raise UserError(_("Part %s already exists.\nClose with OK to reuse, with Cancel to discharge." % (self.name)))
            if not self.engineering_code:
                self.engineering_code = self.name

    @api.onchange('tmp_material')
    def on_change_tmpmater(self):
        if self.tmp_material:
            if self.tmp_material.name:
                self.engineering_material = unicode(self.tmp_material.name)

    @api.onchange('tmp_treatment')
    def on_change_tmptreatment(self):
        if self.tmp_treatment:
            if self.tmp_treatment.name:
                self.engineering_treatment = unicode(self.tmp_treatment.name)

    @api.onchange('tmp_surface')
    def on_change_tmpsurface(self):
        if self.tmp_surface:
            if self.tmp_surface.name:
                self.engineering_surface = unicode(self.tmp_surface.name)

#   Internal methods
    def _packfinalvalues(self, fmt, value=False, value2=False, value3=False):
        """
            Pack a string formatting it like specified in fmt
            mixing both label and value or only label.
        """
        retvalue = ''
        if value3:
            if isinstance(value3, float):
                svalue3 = "%g" % value3
            else:
                svalue3 = value3
        else:
            svalue3 = ''

        if value2:
            if isinstance(value2, float):
                svalue2 = "%g" % value2
            else:
                svalue2 = value2
        else:
            svalue2 = ''

        if value:
            if isinstance(value, float):
                svalue = "%g" % value
            else:
                svalue = value
        else:
            svalue = ''

        if svalue or svalue2 or svalue3:
            cnt = fmt.count('%s')
            if cnt == 3:
                retvalue = fmt % (svalue, svalue2, svalue3)
            if cnt == 2:
                retvalue = fmt % (svalue, svalue2)
            elif cnt == 1:
                retvalue = fmt % (svalue)
        return retvalue

    def _packvalues(self, fmt, label=False, value=False):
        """
            Pack a string formatting it like specified in fmt
            mixing both label and value or only label.
        """
        retvalue = ''
        if value:
            if isinstance(value, float):
                svalue = "%g" % value
            else:
                svalue = value
        else:
            svalue = ''

        if label:
            if isinstance(label, float):
                slabel = "%g" % label
            else:
                slabel = label
        else:
            slabel = ''

        if svalue:
            cnt = fmt.count('%s')

            if cnt == 2:
                retvalue = fmt % (slabel, svalue)
            elif cnt == 1:
                retvalue = fmt % (svalue)
        return retvalue

    def computeDescription(self, thisObject, initialVal, std_umc1, std_umc2, std_umc3, std_value1, std_value2, std_value3):
        description1 = False
        description2 = False
        description3 = False
        description = initialVal
        if thisObject.fmtend:
            if std_umc1 and std_value1:
                description1 = self._packvalues(thisObject.fmt1, std_umc1, std_value1)
            if std_umc2 and std_value2:
                description2 = self._packvalues(thisObject.fmt2, std_umc2, std_value2)
            if std_umc3 and std_value3:
                description3 = self._packvalues(thisObject.fmt3, std_umc3, std_value3)
            description = description + " " + self._packfinalvalues(thisObject.fmtend, description1, description2, description3)
        else:
            if std_umc1 and std_value1:
                description = description + " " + self._packvalues(thisObject.fmt1, std_umc1, std_value1)
            if std_umc2 and std_value2:
                description = description + " " + self._packvalues(thisObject.fmt2, std_umc2, std_value2)
            if std_umc3 and std_value3:
                description = description + " " + self._packvalues(thisObject.fmt3, std_umc3, std_value3)
        if thisObject.unitab:
            description = description + " " + thisObject.unitab
        return description

    @api.model
    def _getbyrevision(self, name, revision):
        return self.search([('engineering_code', '=', name),
                            ('engineering_revision', '=', revision)])

    @api.multi
    def product_template_open(self):
        product_id = self.product_tmpl_id.id
        mod_obj = self.env['ir.model.data']
        search_res = mod_obj.get_object_reference('plm', 'product_template_form_view_plm_custom')
        form_id = search_res and search_res[1] or False
        if product_id and form_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Product Engineering'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'product.template',
                'res_id': product_id,
                'views': [(form_id, 'form')],
            }

    @api.multi
    def open_boms(self):
        product_tmpl_id = self.product_tmpl_id.id
        if product_tmpl_id:
            localCtx = self.env.context.copy()
            localCtx.update({'default_product_tmpl_id': product_tmpl_id, 'search_default_product_tmpl_id': product_tmpl_id})
            return {'type': 'ir.actions.act_window',
                    'name': _('Mrp Bom'),
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': 'mrp.bom',
                    'context': localCtx,
                    }

    @api.model
    def _getChildrenBom(self, component, level=0, currlevel=0):
        """
            Return a flat list of each child, listed once, in a Bom ( level = 0 one level only, level = 1 all levels)
        """
        result = []
        bufferdata = []
        if level == 0 and currlevel > 1:
            return bufferdata
        for bomid in component.product_tmpl_id.bom_ids:
            for bomline in bomid.bom_line_ids:
                children = self._getChildrenBom(bomline.product_id, level, currlevel + 1)
                bufferdata.extend(children)
                bufferdata.append(bomline.product_id.id)
        result.extend(bufferdata)
        return list(set(result))

    @api.model
    def RegMessage(self, request, default=None):
        """
            Registers a message for requested component
        """
        oid, message = request
        self.wf_message_post([oid], body=_(message))
        return False

    @api.model
    def getLastTime(self, oid, default=None):
        return self.getUpdTime(self.browse(oid))

    def getUpdTime(self, obj):
        if(obj.write_date is not False):
            return datetime.strptime(obj.write_date, '%Y-%m-%d %H:%M:%S')
        else:
            return datetime.strptime(obj.create_date, '%Y-%m-%d %H:%M:%S')

    @api.multi
    def Clone(self, defaults={}):
        exitValues = {}
        newCompBrws = self.copy(defaults)
        if newCompBrws not in (None, False):
            exitValues['_id'] = newCompBrws.id
            exitValues['name'] = newCompBrws.name
            exitValues['engineering_code'] = newCompBrws.engineering_code
            exitValues['engineering_revision'] = newCompBrws.engineering_revision
        return exitValues

    @api.model
    def GetUpdated(self, vals):
        """
            Get Last/Requested revision of given items (by name, revision, update time)
        """
        partData, attribNames, forceCADProperties = vals
        ids = self.GetLatestIds(partData, forceCADProperties=forceCADProperties)
        return self.read(list(set(ids)), attribNames)

    @api.model
    def GetLatestIds(self, vals, forceCADProperties=False):
        """
            Get Last/Requested revision of given items (by name, revision, update time)
        """
        ids = []
        plmDocObj = self.env['plm.document']

        def getCompIds(partName, partRev):
            if docRev is None or docRev is False:
                partIds = self.search([('engineering_code', '=', partName)],
                                      order='engineering_revision').ids
                if len(partIds) > 0:
                    ids.append(partIds[-1])
            else:
                ids.extend(self.search([('engineering_code', '=', partName),
                                        ('engineering_revision', '=', partRev)]).ids)

        for docName, docRev, docIdToOpen in vals:
            checkOutUser = plmDocObj.get_checkout_user(docIdToOpen)
            if checkOutUser:
                isMyDocument = plmDocObj.isCheckedOutByMe(docIdToOpen)
                if isMyDocument and forceCADProperties:
                    return []    # Document properties will be not updated
                else:
                    getCompIds(docName, docRev)
            else:
                getCompIds(docName, docRev)
        return list(set(ids))

    @api.multi
    def NewRevision(self):
        """
            create a new revision of current component
        """
        newID = None
        newIndex = 0
        for tmpObject in self:
            latestIDs = self.GetLatestIds([(tmpObject.engineering_code, tmpObject.engineering_revision, False)])
            for oldObject in self.browse(latestIDs):
                newIndex = int(oldObject.engineering_revision) + 1
                defaults = {}
                defaults['engineering_writable'] = False
                defaults['state'] = 'undermodify'
                self.write([oldObject.id], defaults)
                self.wf_message_post([oldObject.id], body=_('Status moved to: %s.' % (USEDIC_STATES[defaults['state']])))
                # store updated infos in "revision" object
                defaults['name'] = oldObject.name                 # copy function needs an explicit name value
                defaults['engineering_revision'] = newIndex
                defaults['engineering_writable'] = True
                defaults['state'] = 'draft'
                defaults['linkeddocuments'] = []                  # Clean attached documents for new revision object
                newCompBrws = oldObject.copy(defaults)
                self.wf_message_post([oldObject.id], body=_('Created : New Revision.'))
                newCompBrws.write({'name': oldObject.name})
                # create a new "old revision" object
                break
            break
        return (newID, newIndex)

    @api.model
    def SaveOrUpdate(self, vals):
        """
            Save or Update Parts
        """
        listedParts = []
        retValues = []
        for partVals in vals:
            hasSaved = False
            if partVals.get('engineering_code', '') in listedParts:
                continue
            if 'engineering_code' not in partVals or 'engineering_revision' not in partVals:
                partVals['componentID'] = False
                partVals['hasSaved'] = hasSaved
                continue
            existingCompBrws = self.search([('engineering_code', '=', partVals['engineering_code']),
                                            ('engineering_revision', '=', partVals['engineering_revision'])])
            if not existingCompBrws:
                existingCompBrws = self.create(partVals)
                hasSaved = True
            else:
                partVals['name'] = existingCompBrws.name
                if (self.getUpdTime(existingCompBrws) < datetime.strptime(partVals['lastupdate'], '%Y-%m-%d %H:%M:%S')):
                    if self._iswritable(existingCompBrws):
                        del(partVals['lastupdate'])
                        if not existingCompBrws.write(partVals):
                            raise UserError(_("Part %r cannot be updated" % (partVals['engineering_code'])))
                        hasSaved = True
            partVals['componentID'] = existingCompBrws.id
            partVals['hasSaved'] = hasSaved
            retValues.append(partVals)
            listedParts.append(partVals['engineering_code'])
        return retValues

    @api.model
    def QueryLast(self, request=([], []), default=None):
        """
            Query to return values based on columns selected.
        """
        objId = False
        expData = []
        queryFilter, columns = request
        if len(columns) < 1:
            return expData
        if 'engineering_revision' in queryFilter:
            del queryFilter['engineering_revision']
        allIDs = self.search(queryFilter,
                             order='engineering_revision').ids
        if len(allIDs) > 0:
            allIDs.sort()
            objId = allIDs[len(allIDs) - 1]
        if objId:
            tmpData = self.export_data([objId], columns)
            if 'datas' in tmpData:
                expData = tmpData['datas']
        return expData

    @api.model
    def create_bom_from_ebom(self, objProductProductBrw, newBomType, summarize=False):
        """
            create a new bom starting from ebom
        """
        bomType = self.env['mrp.bom']
        bomLType = self.env['mrp.bom.line']
        prodTmplObj = self.env['product.template']
        collectList = []

        def getPreviousNormalBOM(bomBrws):
            outBomBrws = []
            engineering_revision = bomBrws.engineering_revision
            if engineering_revision <= 0:
                return []
            engineering_code = bomBrws.product_tmpl_id.engineering_code
            previousRevProductBrwsList = prodTmplObj.search([('engineering_revision', '=', engineering_revision - 1),
                                                             ('engineering_code', '=', engineering_code)])
            for prodBrws in previousRevProductBrwsList:
                oldBomBrwsList = bomType.search([('product_tmpl_id', '=', prodBrws.id),
                                                 ('type', '=', newBomType)])
                for oldBomBrws in oldBomBrwsList:
                    outBomBrws.append(oldBomBrws)
                break
            return outBomBrws

        eBomId = False
        newidBom = False
        if newBomType not in ['normal', 'phantom']:
            raise UserError(_("Could not convert source bom to %r" % newBomType))
        product_template_id = objProductProductBrw.product_tmpl_id.id
        bomBrwsList = bomType.search([('product_tmpl_id', '=', product_template_id),
                                      ('type', '=', newBomType)])
        if bomBrwsList:
            for bomBrws in bomBrwsList:
                for bom_line in bomBrws.bom_line_ids:
                    self.create_bom_from_ebom(bom_line.product_id, newBomType, summarize)
                break
        else:
            engBomBrwsList = bomType.search([('product_tmpl_id', '=', product_template_id),
                                             ('type', '=', 'ebom')])
            if not engBomBrwsList:
                UserError(_("No Enginnering bom provided"))
            for eBomBrws in engBomBrwsList:
                newBomBrws = eBomBrws.copy({})
                newBomBrws.write({'name': objProductProductBrw.name,
                                  'product_tmpl_id': product_template_id,
                                  'type': newBomType,
                                  'ebom_source_id': eBomId,
                                  },
                                 check=False)
                ok_rows = self._summarizeBom(newBomBrws.bom_line_ids)
                # remove not summarized lines
                for bom_line in list(set(newBomBrws.bom_line_ids) ^ set(ok_rows)):
                    bom_line.unlink()
                # update the quantity with the summarized values
                for bom_line in ok_rows:
                    bom_line.write({'type': newBomType,
                                    'source_id': False,
                                    'product_qty': bom_line.product_qty,
                                    'ebom_source_id': eBomId,
                                    })
                    self.create_bom_from_ebom(bom_line.product_id, newBomType)
                self.wf_message_post([objProductProductBrw.id], body=_('Created %r' % newBomType))
                break
        if newidBom and eBomId:
            bomBrws = bomType.browse(eBomId)
            oldBomList = getPreviousNormalBOM(bomBrws)
            for oldNBom in oldBomList:
                newBomBrws = newidBom
                if oldNBom != oldBomList[-1]:       # Because in the previous loop I already have a copy of the normal BOM
                    newBomBrws = bomType.copy(newidBom)
                collectList.extend(self.addOldBomLines(oldNBom, newBomBrws, bomLType, newBomType, bomBrws, bomType, summarize))
        return collectList

    @api.model
    def addOldBomLines(self, oldNBom, newBomBrws, bomLineObj, newBomType, bomBrws, bomType, summarize=False):
        collectList = []

        def verifySummarize(product_id, old_prod_qty):
            toReturn = old_prod_qty, False
            for newLine in newBomBrws.bom_line_ids:
                if newLine.product_id.id == product_id:
                    templateName = newBomBrws.product_tmpl_id.name
                    product_name = newLine.product_id.name
                    outMsg = 'In BOM "%s" ' % (templateName)
                    toReturn = 0, False
                    if summarize:
                        outMsg = outMsg + 'line "%s" has been summarized.' % (product_name)
                        toReturn = newLine.product_qty + old_prod_qty, newLine.id
                    else:
                        outMsg = outMsg + 'line "%s" has been not summarized.' % (product_name)
                        toReturn = newLine.product_qty, newLine.id
                    collectList.append(outMsg)
                    return toReturn
            return toReturn

        for oldBrwsLine in oldNBom.bom_line_ids:
            if not oldBrwsLine.ebom_source_id:
                qty, foundLineId = verifySummarize(oldBrwsLine.product_id.id, oldBrwsLine.product_qty)
                if not foundLineId:
                    newbomLineBrws = oldBrwsLine.copy()
                    newbomLineBrws.write({'type': newBomType,
                                          'source_id': False,
                                          'product_qty': oldBrwsLine.product_qty,
                                          'ebom_source_id': False,
                                          })
                    newBomBrws.write({'bom_line_ids': [(4, newbomLineBrws.id, 0)]})
                else:
                    bomLineObj.browse(foundLineId).write({'product_qty': qty})
        return collectList

    @api.model
    def _create_normalBom(self, idd):
        """
            Create a new Normal Bom (recursive on all EBom children)
        """
        defaults = {}
        if idd in self.processedIds:
            return False
        checkObj = self.browse(idd)
        if not checkObj:
            return False
        bomType = self.env['mrp.bom']
        bomLType = self.env['mrp.bom.line']
        product_template_id = checkObj.product_tmpl_id.id
        objBoms = bomType.search([('product_tmpl_id', '=', product_template_id),
                                  ('type', '=', 'normal')])
        if not objBoms:
            bomBrwsList = bomType.search([('product_tmpl_id', '=', product_template_id),
                                          ('type', '=', 'ebom')])
            for bomBrws in bomBrwsList:
                newBomBrws = bomBrws.copy(defaults)
                self.processedIds.append(idd)
                if newBomBrws:
                    newBomBrws.write({'name': checkObj.name,
                                      'product_id': checkObj.id,
                                      'type': 'normal'},
                                     check=False)
                    ok_rows = self._summarizeBom(newBomBrws.bom_line_ids)
                    for bom_line in list(set(newBomBrws.bom_line_ids) ^ set(ok_rows)):
                        bom_line.unlink()
                    for bom_line in ok_rows:
                        bomLType.browse([bom_line.id]).write({'type': 'normal',
                                                              'source_id': False,
                                                              'name': bom_line.product_id.name,
                                                              'product_qty': bom_line.product_qty})
                        self._create_normalBom(bom_line.product_id.id)
        else:
            for objBom in objBoms:
                for bom_line in objBom.bom_line_ids:
                    self._create_normalBom(bom_line.product_id.id)
        return False

    @api.model
    def _summarizeBom(self, datarows):
        dic = {}
        for datarow in datarows:
            key = str(datarow.product_id.id)
            if key in dic:
                dic[key].product_qty = float(dic[key].product_qty) + float(datarow.product_qty)
            else:
                dic[key] = datarow
        retd = dic.values()
        return retd

    @api.multi
    def _get_recursive_parts(self, excludeStatuses, includeStatuses):
        """
           Get all ids related to current one as children
        """
        errors = []
        tobeReleasedIDs = []
        if not isinstance(self.ids, (list, tuple)):
            ids = [self.ids]
        tobeReleasedIDs.extend(ids)
        for prodBrws in self:
            for childProdBrws in self.browse(self._getChildrenBom(prodBrws, 1)):
                if (childProdBrws.state not in excludeStatuses) and (childProdBrws.state not in includeStatuses):
                    errors.append(_("Product code: %r revision %r status %r") % (childProdBrws.engineering_code, childProdBrws.engineering_revision, childProdBrws.state))
                    continue
                if childProdBrws.state in includeStatuses:
                    if childProdBrws.id not in tobeReleasedIDs:
                        tobeReleasedIDs.append(childProdBrws.id)
        msg = ''
        if errors:
            msg = _("Unable to perform workFlow action due")
            for subMsg in errors:
                msg = msg + "\n" + subMsg
        return (msg, list(set(tobeReleasedIDs)))

    @api.multi
    def action_create_normalBom_WF(self):
        """
            Create a new Normal Bom if doesn't exist (action callable from code)
        """
        for prodId in self.ids:
            self.processedIds = []
            self._create_normalBom(prodId)
        self.wf_message_post(body=_('Created Normal Bom.'))
        return False

    @api.multi
    def _action_ondocuments(self, action_name):
        """
            move workflow on documents having the same state of component
        """
        docIDs = []
        docInError = []
        documentType = self.env['plm.document']
        for oldObject in self:
            if (action_name != 'transmit') and (action_name != 'reject') and (action_name != 'release'):
                check_state = oldObject.state
            else:
                check_state = 'confirmed'
            for documentBrws in oldObject.linkeddocuments:
                if documentBrws.state == check_state:
                    if documentBrws.is_checkout:
                        docInError.append(_("Document %r : %r is checked out by user %r") % (documentBrws.name, documentBrws.revisionid, documentBrws.checkout_user))
                        continue
                    if documentBrws.id not in docIDs:
                        docIDs.append(documentBrws.id)
        if docInError:
            msg = "Error on workflow operation"
            for e in docInError:
                msg = msg + "\n" + e
            raise UserError(msg)

        if len(docIDs) > 0:
            if action_name == 'confirm':
                documentType.signal_workflow(docIDs, action_name)
            elif action_name == 'transmit':
                documentType.signal_workflow(docIDs, 'confirm')
            elif action_name == 'draft':
                documentType.signal_workflow(docIDs, 'correct')
            elif action_name == 'correct':
                documentType.signal_workflow(docIDs, action_name)
            elif action_name == 'reject':
                documentType.signal_workflow(docIDs, 'correct')
            elif action_name == 'release':
                documentType.signal_workflow(docIDs, action_name)
            elif action_name == 'undermodify':
                documentType.action_cancel(docIDs)
            elif action_name == 'suspend':
                documentType.action_suspend(docIDs)
            elif action_name == 'reactivate':
                documentType.signal_workflow(docIDs, 'release')
            elif action_name == 'obsolete':
                documentType.signal_workflow(docIDs, action_name)
        return docIDs

    @api.model
    def _iswritable(self, oid):
        checkState = ('draft')
        if not oid.engineering_writable:
            logging.warning("_iswritable : Part (%r - %d) is not writable." % (oid.engineering_code, oid.engineering_revision))
            return False
        if oid.state not in checkState:
            logging.warning("_iswritable : Part (%r - %d) is in status %r." % (oid.engineering_code, oid.engineering_revision, oid.state))
            return False
        if not oid.engineering_code:
            logging.warning("_iswritable : Part (%r - %d) is without Engineering P/N." % (oid.name, oid.engineering_revision))
            return False
        return True

    @api.multi
    def wf_message_post(self, body=''):
        """
            Writing messages to follower, on multiple objects
        """
        if not (body == ''):
            for prodId in self.ids:
                self.message_post([prodId], body=_(body))

    @api.multi
    def action_draft(self):
        """
            release the object
        """
        defaults = {}
        status = 'draft'
        action = 'draft'
        docaction = 'draft'
        defaults['engineering_writable'] = True
        defaults['state'] = status
        excludeStatuses = ['draft', 'released', 'undermodify', 'obsoleted']
        includeStatuses = ['confirmed', 'transmitted']
        return self._action_to_perform(status, action, docaction, defaults, excludeStatuses, includeStatuses)

    @api.multi
    def action_confirm(self):
        """
            action to be executed for Draft state
        """
        defaults = {}
        status = 'confirmed'
        action = 'confirm'
        docaction = 'confirm'
        defaults['engineering_writable'] = False
        defaults['state'] = status
        excludeStatuses = ['confirmed', 'transmitted', 'released', 'undermodify', 'obsoleted']
        includeStatuses = ['draft']
        return self._action_to_perform(status, action, docaction, defaults, excludeStatuses, includeStatuses)

    @api.multi
    def action_release(self):
        """
           action to be executed for Released state
        """
        tmpl_ids = []
        full_ids = []
        defaults = {}
        excludeStatuses = ['released', 'undermodify', 'obsoleted']
        includeStatuses = ['confirmed']
        errors, allIDs = self._get_recursive_parts(excludeStatuses, includeStatuses)
        if len(allIDs) < 1 or len(errors) > 0:
            raise UserError(errors)
        allProdObjs = self.browse(allIDs)
        for oldObject in allProdObjs:
            last_id = self._getbyrevision(oldObject.engineering_code, oldObject.engineering_revision - 1)
            if last_id is not None:
                defaults['engineering_writable'] = False
                defaults['state'] = 'obsoleted'
                prodObj = self.browse([last_id])
                prodObj.write(defaults)
                self.wf_message_post([last_id], body=_('Status moved to: %s.' % (USEDIC_STATES[defaults['state']])))
            defaults['engineering_writable'] = False
            defaults['state'] = 'released'
        self._action_ondocuments(allIDs, 'release')
        for currId in allProdObjs:
            if not(currId.id in self.ids):
                tmpl_ids.append(currId.product_tmpl_id.id)
            full_ids.append(currId.product_tmpl_id.id)
        self.signal_workflow(tmpl_ids, 'release')
        objId = self.env['product.template'].browse(full_ids).write(defaults)
        if (objId):
            self.wf_message_post(allIDs, body=_('Status moved to: %s.' % (USEDIC_STATES[defaults['state']])))
        return objId

    @api.multi
    def action_obsolete(self):
        """
            obsolete the object
        """
        defaults = {}
        status = 'obsoleted'
        action = 'obsolete'
        docaction = 'obsolete'
        defaults['engineering_writable'] = False
        defaults['state'] = status
        excludeStatuses = ['draft', 'confirmed', 'transmitted', 'undermodify', 'obsoleted']
        includeStatuses = ['released']
        return self._action_to_perform(status, action, docaction, defaults, excludeStatuses, includeStatuses)

    @api.multi
    def action_reactivate(self):
        """
            reactivate the object
        """
        defaults = {}
        status = 'released'
        action = ''
        docaction = 'release'
        defaults['engineering_writable'] = True
        defaults['state'] = status
        excludeStatuses = ['draft', 'confirmed', 'transmitted', 'released', 'undermodify', 'obsoleted']
        includeStatuses = ['obsoleted']
        return self._action_to_perform(status, action, docaction, defaults, excludeStatuses, includeStatuses)

    @api.multi
    def _action_to_perform(self, status, action, docaction, defaults=[], excludeStatuses=[], includeStatuses=[]):
        tmpl_ids = []
        full_ids = []
        userErrors, allIDs = self._get_recursive_parts(excludeStatuses, includeStatuses)
        if userErrors:
            raise UserError(userErrors)
        self._action_ondocuments(allIDs, docaction)
        for currId in self:
            if not(currId.id in self.ids):
                tmpl_ids.append(currId.product_tmpl_id.id)
            full_ids.append(currId.product_tmpl_id.id)
        if action:
            self.signal_workflow(tmpl_ids, action)
        objId = self.env['product.template'].browse(full_ids).write(defaults)
        if objId:
            self.wf_message_post(allIDs, body=_('Status moved to: %s.' % (USEDIC_STATES[defaults['state']])))
        return objId

#  ######################################################################################################################################33

    @api.model
    def create(self, vals):
        if not vals:
            raise ValidationError(_("""You are trying to create a product without values"""))
        if ('name' in vals):
            if not vals['name']:
                return False
            prodBrwsList = self.search([('name', '=', vals['name'])],
                                       order='engineering_revision')
            if 'engineering_code' in vals:
                if vals['engineering_code'] == False:
                    vals['engineering_code'] = vals['name']
            else:
                vals['engineering_code'] = vals['name']
            if prodBrwsList:
                existObj = prodBrwsList[len(prodBrwsList) - 1]
                if ('engineering_revision' in vals):
                    if existObj:
                        if vals['engineering_revision'] > existObj.engineering_revision:
                            vals['name'] = existObj.name
                        else:
                            return existObj
                else:
                    return existObj
        try:
            return super(plm_component, self).create(vals)
        except Exception, ex:
            import psycopg2
            if isinstance(ex, psycopg2.IntegrityError):
                raise ex
            raise ValidationError(_(" (%r). It has tried to create with values : (%r).") % (ex, vals))

    @api.multi
    def copy(self, defaults={}):
        """
            Overwrite the default copy method
        """
        previous_name = self.name
        if not defaults.get('name', False):
            defaults['name'] = '-'                   # If field is required super of clone will fail returning False, this is the case
            defaults['engineering_code'] = '-'
            defaults['engineering_revision'] = 0
        # assign default value
        defaults['state'] = 'draft'
        defaults['engineering_writable'] = True
        defaults['write_date'] = None
        defaults['linkeddocuments'] = []
        objId = super(plm_component, self).copy(defaults)
        if (objId):
            self.wf_message_post(body=_('Copied starting from : %s.' % previous_name))
        return objId

    @api.multi
    def unlink(self):
        values = {'state': 'released'}
        checkState = ('undermodify', 'obsoleted')
        for checkObj in self:
            prodBrwsList = self.search([('engineering_code', '=', checkObj.engineering_code),
                                        ('engineering_revision', '=', checkObj.engineering_revision - 1)])
            if len(prodBrwsList) > 0:
                oldObject = prodBrwsList[0]
                if oldObject.state in checkState:
                    self.wf_message_post([oldObject.id], body=_('Removed : Latest Revision.'))
                    if not self.browse([oldObject.id]).write(values):
                        logging.warning("unlink : Unable to update state to old component (%r - %d)." % (oldObject.engineering_code, oldObject.engineering_revision))
                        return False
        return super(plm_component, self).unlink()

    @api.model
    def translateForClient(self, values=[], forcedLang=''):
        '''
            Get values attribute in this format:
            values = [{'field1':value1,'field2':value2,...}]     only one element in the list!!!
            and return computed values due to language
            Get also forcedLang attribute in this format:
            forcedLang = 'en_US'
            if is not set it takes language from user
        '''
        language = forcedLang
        if not forcedLang:
            resDict = self.env['res.users'].read(['lang'])
            language = resDict.get('lang', '')
        if values:
            values = values[0]
        if language and values:
            toRead = filter(lambda x: type(x) in [str, unicode] and x, values.values())     # Where computed only string and not null string values (for performance improvement)
            toRead = list(set(toRead))                                                      # Remove duplicates
            for fieldName, valueToTranslate in values.items():
                if valueToTranslate not in toRead:
                    continue
                translationObj = self.env['ir.translation']
                translationBrwsList = translationObj.search([('lang', '=', language),
                                                             ('src', '=', valueToTranslate)])
                if translationBrwsList:
                    readDict = translationBrwsList[0].read(['value'])
                    values[fieldName] = readDict.get('value', '')
        return values

    @api.multi
    def action_rev_docs(self):
        '''
            This function is called by the button on component view, section LinkedDocuments
            Clicking that button all documents related to all revisions of this component are opened in a tree view
        '''
        docIds = []
        for compBrws in self:
            engineering_code = compBrws.engineering_code
            if not engineering_code:
                logging.warning("Part %s doesn't have and engineering code!" % (compBrws.name))
                continue
            compBrwsList = self.search([('engineering_code', '=', engineering_code)])
            for compBrws in compBrwsList:
                docIds.extend(compBrws.linkeddocuments.ids)
        return {'domain': [('id', 'in', docIds)],
                'name': _('Related documents'),
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'plm.document',
                'type': 'ir.actions.act_window',
                }

        def name_search(self, cr, user, name='', args=None, operator='ilike', context=None, limit=100):
            result = super(plm_component, self).name_search(cr, user, name, args, operator, context, limit)
            newResult = []
            for productId, oldName in result:
                objBrowse = self.browse(cr, user, [productId], context)
                newName = "%r [%r] " % (oldName, objBrowse.engineering_revision)
                newResult.append((productId, newName))
            return newResult

    @api.multi
    def _father_part_compute(self, name='', arg={}):
        """ Gets father bom.
        @param self: The object pointer
        @param cr: The current row, from the database cursor,
        @param uid: The current user ID for security checks
        @param ids: List of selected IDs
        @param name: Name of the field
        @param arg: User defined argument
        @param context: A standard dictionary for contextual values
        @return:  Dictionary of values
        """
        bom_line_objType = self.env['mrp.bom.line']
        prod_objs = self.browse(self.ids)
        for prod_obj in prod_objs:
            prod_ids = []
            bom_line_objs = bom_line_objType.search([('product_id', '=', prod_obj.id)])
            for bom_line_obj in bom_line_objs:
                for objPrd in self.search([('product_tmpl_id', '=', bom_line_obj.bom_id.product_tmpl_id.id)]):
                    prod_ids.append(objPrd.id)
            prod_obj.father_part_ids = prod_ids

plm_component()


class ProductTemporaryNormalBom(osv.osv.osv_memory):
    _name = "plm.temporary"
    _description = "Temporary Class"
    name = fields.Char(_('Temp'), size=128)
    summarize = fields.Boolean('Summarize Bom Lines if needed.', help="If set as true, when a Bom line comes from EBOM was in the old normal BOM two lines where been summarized.")

    @api.multi
    def action_create_normalBom(self):
        """
            Create a new Normal Bom if doesn't exist (action callable from views)
        """
        selectdIds = self.env.context.get('active_ids', [])
        objType = self.env.context.get('active_model', '')
        if objType != 'product.product':
            raise UserError(_("The creation of the normalBom works only on product_product object"))
        if not selectdIds:
            raise UserError(_("Select a product before to continue"))
        objType = self.env.context.get('active_model', False)
        product_product_type_object = self.env[objType]
        for productBrowse in product_product_type_object.browse(selectdIds):
            idTemplate = productBrowse.product_tmpl_id.id
            objBoms = self.env['mrp.bom'].search([('product_tmpl_id', '=', idTemplate),
                                                  ('type', '=', 'normal')])
            if objBoms:
                raise UserError(_("Normal BoM for Part %r already exists." % (objBoms)))
            lineMessaggesList = product_product_type_object.create_bom_from_ebom(productBrowse, 'normal', self.summarize)
            if lineMessaggesList:
                outMess = ''
                for mess in lineMessaggesList:
                    outMess = outMess + '\n' + mess
                t_mess_obj = self.pool.get("plm.temporary.message")
                t_mess_id = t_mess_obj.create({'name': outMess})
                return {'name': _('Result'),
                        'view_type': 'form',
                        "view_mode": 'form',
                        'res_model': "plm.temporary.message",
                        'res_id': t_mess_id,
                        'type': 'ir.actions.act_window',
                        'target': 'new',
                        }
        return {}
ProductTemporaryNormalBom()


class plm_temporary_message(osv.osv.osv_memory):
    _name = "plm.temporary.message"
    _description = "Temporary Class"
    name = fields.Text(_('Bom Result'), readonly=True)

plm_temporary_message()


class ProductProductDashboard(models.Model):
    _name = "report.plm_component"
    _description = "Report Component"
    _auto = False
    count_component_draft = fields.Integer(_('Draft'),
                                           readonly=True,
                                           translate=True)
    count_component_confirmed = fields.Integer(_('Confirmed'),
                                               readonly=True,
                                               translate=True)
    count_component_released = fields.Integer(_('Released'),
                                              readonly=True,
                                              translate=True)
    count_component_modified = fields.Integer(_('Under Modify'),
                                              readonly=True,
                                              translate=True)
    count_component_obsoleted = fields.Integer(_('Obsoleted'),
                                               readonly=True,
                                               translate=True)

    def init(self, cr):
        tools.drop_view_if_exists(cr, 'report_plm_component')
        cr.execute("""
            CREATE OR REPLACE VIEW report_plm_component AS (
                SELECT
                    (SELECT min(id) FROM product_template) as id,
                    (SELECT count(*) FROM product_template WHERE state = 'draft') AS count_component_draft,
                    (SELECT count(*) FROM product_template WHERE state = 'confirmed') AS count_component_confirmed,
                    (SELECT count(*) FROM product_template WHERE state = 'released') AS count_component_released,
                    (SELECT count(*) FROM product_template WHERE state = 'undermodify') AS count_component_modified,
                    (SELECT count(*) FROM product_template WHERE state = 'obsoleted') AS count_component_obsoleted
             )
        """)

ProductProductDashboard()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
