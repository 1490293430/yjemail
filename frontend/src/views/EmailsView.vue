<template>
  <div class="page-container">
    <div class="emails-container">
      <el-card class="email-list-card shadow">
        <template #header>
          <div class="card-header flex-between">
            <div class="title-area flex gap-md" style="align-items: center;">
              <h2 class="page-title">邮箱列表</h2>
              <el-tooltip content="开启后，所有 Outlook 邮箱将使用 Graph API 方式收信" placement="top">
                <div class="graph-api-switch flex gap-sm" style="align-items: center; margin-left: 16px;">
                  <span style="font-size: 13px; color: #909399;">
                    邮箱: {{ outlookEmailCount }} | 订阅: {{ subscriptionCount }}<span v-if="expiredCount > 0" style="color: #F56C6C;"> | 过期: {{ expiredCount }}</span>
                  </span>
                  <el-button
                    v-if="outlookEmailCount > subscriptionCount"
                    type="primary"
                    size="small"
                    link
                    @click="createMissingSubscriptions"
                    :loading="creatingSubscriptions"
                    style="margin-left: 4px;"
                  >
                    补订阅
                  </el-button>
                  <span style="font-size: 14px; color: #606266; margin-left: 8px;">Graph API</span>
                  <el-switch
                    v-model="globalUseGraphApi"
                    @change="handleGlobalGraphApiChange"
                  />
                </div>
              </el-tooltip>
              <el-button type="warning" size="small" @click="exportAllEmails" :icon="Download" style="margin-left: 12px;">
                导出全部邮箱
              </el-button>
            </div>
            <div class="actions flex gap-md">
              <el-button type="primary" @click="refreshEmails" :icon="Refresh" class="hover-scale">
                刷新列表
              </el-button>
              <el-button type="success" @click="showAddEmailDialog" :icon="Plus" class="hover-scale">
                添加邮箱
              </el-button>
            </div>
          </div>
        </template>

        <div class="toolbar flex gap-md mb-4">
          <el-button
            type="danger"
            :disabled="!hasSelectedEmails"
            @click="handleBatchDelete"
            :icon="Delete"
            class="hover-scale"
          >
            批量删除
          </el-button>
          <el-button
            type="primary"
            :disabled="!hasSelectedEmails"
            @click="handleBatchCheck"
            :icon="Download"
            class="hover-scale"
          >
            批量收信
          </el-button>
          <el-button
            type="success"
            @click="handleBatchCheckUnchecked"
            :icon="Download"
            class="hover-scale"
            :loading="batchCheckingUnchecked"
          >
            检查未收信邮箱
          </el-button>
          <el-button
            type="danger"
            @click="clearErrorEmails"
            :icon="Delete"
            class="hover-scale"
            v-if="errorEmailCount > 0"
          >
            清除异常邮箱 ({{ errorEmailCount }})
          </el-button>
          <el-button
            type="warning"
            @click="showRenamePlatformDialog"
            :icon="Edit"
            class="hover-scale"
            v-if="allPlatforms.length > 0"
          >
            重命名平台
          </el-button>
          
          <!-- 平台筛选 -->
          <div class="platform-filter flex gap-sm" style="margin-left: auto; align-items: center;">
            <span style="font-size: 14px; color: #606266;">筛选平台:</span>
            <el-select
              v-model="filterPlatform"
              placeholder="选择平台"
              clearable
              style="width: 160px;"
              @change="handlePlatformFilterChange"
            >
              <el-option
                v-for="p in allPlatforms"
                :key="p.platform_name"
                :label="`${p.platform_name} (${p.count})`"
                :value="p.platform_name"
              />
            </el-select>
            <el-radio-group v-model="filterPlatformMode" size="small" @change="handlePlatformFilterChange" :disabled="!filterPlatform">
              <el-radio-button label="has">已注册</el-radio-button>
              <el-radio-button label="not">未注册</el-radio-button>
            </el-radio-group>
            <el-button 
              type="success" 
              size="small" 
              @click="exportFilteredEmails" 
              :icon="Download"
              :disabled="!filterPlatform"
            >
              导出邮箱
            </el-button>
          </div>
        </div>

        <div class="search-bar mb-4">
          <el-input
            v-model="emailSearchFilter"
            placeholder="搜索邮箱..."
            clearable
            style="width: 300px;"
            :prefix-icon="Search"
          />
        </div>

        <el-table
          v-loading="loading"
          :data="filteredEmails"
          @selection-change="handleSelectionChange"
          @header-dragend="handleHeaderDragend"
          style="width: 100%"
          stripe
          border
          highlight-current-row
          class="email-table"
        >
          <el-table-column
            type="selection"
            width="55"
            :selectable="row => row"
          />
          <el-table-column prop="email" label="邮箱地址" :width="columnWidths.email" resizable>
            <template #default="scope">
              <div class="email-cell">
                <el-tooltip v-if="scope.row.last_error" :content="scope.row.last_error" placement="top">
                  <el-icon class="error-icon"><WarningFilled /></el-icon>
                </el-tooltip>
                <span class="email-text" :class="{ 'email-error': scope.row.last_error }">{{ scope.row.email }}</span>
                <el-button
                  type="primary"
                  link
                  size="small"
                  :icon="CopyDocument"
                  @click.stop="copyEmail(scope.row.email)"
                  class="copy-btn"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="password" label="密码" :width="columnWidths.password" resizable>
            <template #default="scope">
              <div class="password-field flex-between">
                <span class="password-text">{{ scope.row.showPassword ? scope.row.password : '******' }}</span>
                <el-button
                  type="primary"
                  link
                  :icon="scope.row.showPassword ? Hide : View"
                  @click="togglePasswordVisibility(scope.row)"
                  :loading="scope.row.passwordLoading"
                  class="password-toggle-btn"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="platforms" label="已注册平台" :width="columnWidths.platforms" resizable>
            <template #default="scope">
              <div class="platforms-cell">
                <el-tag
                  v-for="platform in (scope.row.platforms || [])"
                  :key="platform"
                  size="small"
                  closable
                  @close="removePlatform(scope.row.id, platform)"
                  @click="showCorrectPlatformDialog(scope.row, platform)"
                  class="platform-tag clickable"
                  title="点击纠正平台名称"
                >
                  {{ platform }}
                </el-tag>
                <el-button
                  type="primary"
                  link
                  size="small"
                  :icon="Plus"
                  @click.stop="showAddPlatformDialog(scope.row)"
                  class="add-platform-btn"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="last_check_time" label="最后检查时间" :width="columnWidths.last_check_time" resizable>
            <template #default="scope">
              <div v-if="scope.row.last_error" class="error-info">
                <el-tooltip :content="scope.row.last_error" placement="top">
                  <span class="error-text">{{ scope.row.last_error }}</span>
                </el-tooltip>
              </div>
              <span v-else>{{ formatDate(scope.row.last_check_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="mail_type" label="邮箱类型" :width="columnWidths.mail_type" resizable>
            <template #default="scope">
              <el-tag
                :type="getMailTypeColor(scope.row.mail_type || 'outlook')"
                effect="plain"
                class="mail-type-tag"
              >
                {{ getMailTypeName(scope.row.mail_type || 'outlook') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="配置信息" :width="columnWidths.config" resizable>
            <template #default="scope">
              <template v-if="scope.row.mail_type === 'imap'">
                <div class="server-info">
                  <div class="server-field">
                    <strong>服务器:</strong> {{ scope.row.server || 'N/A' }}
                  </div>
                  <div class="port-field">
                    <strong>端口:</strong> {{ scope.row.port || 'N/A' }}
                  </div>
                </div>
              </template>
              <template v-else-if="scope.row.mail_type === 'gmail'">
                <div class="config-info">
                  <div>服务器: imap.gmail.com</div>
                  <div>端口: 993</div>
                </div>
              </template>
              <template v-else-if="scope.row.mail_type === 'qq'">
                <div class="config-info">
                  <div>服务器: imap.qq.com</div>
                  <div>端口: 993</div>
                </div>
              </template>
              <template v-else>
                <div class="config-info">标准配置</div>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" :width="columnWidths.actions" resizable>
            <template #default="scope">
              <div class="action-buttons flex gap-sm">
                <el-button
                  type="primary"
                  size="small"
                  :disabled="isEmailProcessing(scope.row)"
                  @click="handleCheck(scope.row)"
                  class="action-btn"
                >
                  {{ getEmailActionText(scope.row) }}
                </el-button>
                <el-button
                  type="success"
                  size="small"
                  @click="handleViewMails(scope.row)"
                  class="action-btn"
                >
                  查看邮件
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  @click="handleDelete(scope.row)"
                  class="action-btn"
                >
                  删除
                </el-button>
                <el-button
                  type="warning"
                  size="small"
                  @click="handleEdit(scope.row)"
                  class="action-btn"
                >
                  编辑
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 添加邮箱对话框 -->
      <el-dialog
        v-model="addEmailDialogVisible"
        title="添加邮箱"
        width="600px"
        :close-on-click-modal="false"
        class="add-email-dialog"
        destroy-on-close
      >
        <el-tabs v-model="addEmailActiveTab">
          <el-tab-pane label="单个添加" name="single">
            <el-form
              ref="addEmailFormRef"
              :model="addEmailForm"
              :rules="addEmailRules"
              label-width="120px"
              class="add-email-form"
            >
              <el-form-item label="邮箱类型" prop="mail_type">
                <el-select v-model="addEmailForm.mail_type" placeholder="请选择邮箱类型" class="w-full">
                  <el-option
                    v-for="(config, type) in mailTypes"
                    :key="type"
                    :label="config.name"
                    :value="type"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="邮箱地址" prop="email">
                <el-input v-model="addEmailForm.email" placeholder="请输入邮箱地址" />
              </el-form-item>

              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="addEmailForm.password"
                  type="password"
                  placeholder="请输入密码"
                  show-password
                />
              </el-form-item>

              <template v-if="addEmailForm.mail_type === 'outlook'">
                <el-form-item label="Client ID" prop="client_id">
                  <el-input v-model="addEmailForm.client_id" placeholder="请输入Client ID" />
                </el-form-item>

                <el-form-item label="Refresh Token" prop="refresh_token">
                  <el-input v-model="addEmailForm.refresh_token" placeholder="请输入Refresh Token" />
                </el-form-item>
              </template>

              <template v-if="addEmailForm.mail_type === 'imap'">
                <el-form-item label="服务器" prop="server">
                  <el-input v-model="addEmailForm.server" placeholder="请输入IMAP服务器地址" />
                </el-form-item>

                <el-form-item label="端口" prop="port">
                  <el-input-number v-model="addEmailForm.port" :min="1" :max="65535" />
                </el-form-item>

                <el-form-item label="使用SSL" prop="use_ssl">
                  <el-switch v-model="addEmailForm.use_ssl" />
                </el-form-item>
              </template>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="批量添加" name="batch">
            <p class="import-help">请按照以下格式输入邮箱信息，每行一个：<br/>邮箱地址----密码----客户端ID----刷新令牌</p>
            <el-form :model="batchImport" label-width="120px" :rules="batchImportRules" ref="batchImportFormRef">
              <el-form-item label="邮箱类型">
                <el-select v-model="batchImport.mailType" placeholder="请选择邮箱类型">
                  <el-option
                    label="Outlook/Hotmail"
                    value="outlook"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="批量数据" prop="data">
                <el-input
                  v-model="batchImport.data"
                  type="textarea"
                  :rows="10"
                  placeholder="例如: example@outlook.com----password----clientid----refreshtoken"
                />
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>

        <template #footer>
          <span class="dialog-footer">
            <el-button @click="addEmailDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleAddOrImport" :loading="addingEmail || importing">
              确定
            </el-button>
          </span>
        </template>
      </el-dialog>

      <!-- 邮件列表对话框 -->
      <el-dialog
        v-model="mailListDialogVisible"
        title="邮件列表"
        width="90%"
        top="5vh"
        class="mail-list-dialog"
        destroy-on-close
      >
        <div v-if="currentEmail" class="mail-dialog-header flex-between mb-4">
          <h3 class="email-title">
            <span class="text-primary">{{ currentEmail.email }}</span> 的邮件
          </h3>
          <el-button
            type="primary"
            size="small"
            @click="handleCheck(currentEmail)"
            :disabled="isEmailProcessing(currentEmail)"
            :icon="Refresh"
            class="refresh-btn hover-scale"
          >
            刷新邮件
          </el-button>
        </div>

        <el-table
          v-loading="loadingMails"
          :data="mailRecords"
          style="width: 100%"
          stripe
          border
          max-height="60vh"
          class="mail-list-table"
        >
          <el-table-column prop="subject" label="主题" min-width="250" show-overflow-tooltip>
            <template #default="scope">
              <div class="subject-cell">
                <span>{{ scope.row.subject }}</span>
                <el-tag v-if="scope.row.has_attachments" size="small" type="success" class="attachment-tag">
                  <el-icon><Document /></el-icon> 附件
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sender" label="发件人" min-width="200" show-overflow-tooltip />
          <el-table-column prop="received_time" label="接收时间" width="180">
            <template #default="scope">
              <span class="time-field">{{ formatDate(scope.row.received_time) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button
                type="primary"
                size="small"
                @click="viewMailContent(scope.row)"
                :icon="Document"
                class="view-btn"
              >
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-dialog>

      <!-- 邮件内容查看对话框 -->
      <el-dialog
        v-model="mailContentDialogVisible"
        :title="selectedMail ? selectedMail.subject : '邮件详情'"
        width="80%"
        top="5vh"
        class="mail-content-dialog"
      >
        <div v-if="selectedMail" class="mail-detail">
          <!-- 使用EmailContentViewer组件 -->
          <EmailContentViewer
            :mail="selectedMail"
            :attachments="selectedMail.attachments || []"
            :loading-attachments="false"
          />
        </div>
      </el-dialog>

      <!-- 编辑邮箱对话框 -->
      <el-dialog
        v-model="editDialogVisible"
        title="编辑邮箱"
        width="500px"
        @close="resetEditForm"
      >
        <el-form
          ref="editFormRef"
          :model="editForm"
          :rules="editRules"
          label-width="100px"
        >
          <el-form-item label="邮箱地址" prop="email">
            <el-input v-model="editForm.email" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="editForm.password"
              type="password"
              show-password
              @input="checkPasswordStrength"
            >
              <template #append>
                <el-tooltip
                  content="密码应包含大小写字母、数字和特殊字符,长度至少8位"
                  placement="top"
                >
                  <el-icon><InfoFilled /></el-icon>
                </el-tooltip>
              </template>
            </el-input>
            <div class="password-strength" v-if="editForm.password">
              <span>密码强度:</span>
              <el-progress
                :percentage="passwordStrength"
                :color="passwordStrengthColor"
                :format="passwordStrengthText"
              />
            </div>
          </el-form-item>
          <!-- 显示邮箱类型但不能修改 -->
          <el-form-item label="邮箱类型">
            <el-tag :type="getMailTypeColor(editForm.mail_type)">
              {{ getMailTypeName(editForm.mail_type) }}
            </el-tag>
            <div class="form-tips">邮箱类型创建后不可修改</div>
          </el-form-item>
          <template v-if="editForm.mail_type === 'imap'">
            <div class="imap-tips">
              <h4>常用IMAP服务器配置:</h4>
              <p>Gmail: <code>imap.gmail.com</code> 端口: <code>993</code> SSL: 开启</p>
              <p>Outlook: <code>outlook.office365.com</code> 端口: <code>993</code> SSL: 开启</p>
              <p>QQ邮箱: <code>imap.qq.com</code> 端口: <code>993</code> SSL: 开启</p>
              <p>163邮箱: <code>imap.163.com</code> 端口: <code>993</code> SSL: 开启</p>
            </div>
            <el-form-item
              label="服务器"
              prop="server"
            >
              <el-input v-model="editForm.server">
                <template #append>
                  <el-tooltip content="IMAP服务器地址,如: imap.gmail.com" placement="top">
                    <el-icon><InfoFilled /></el-icon>
                  </el-tooltip>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item
              label="端口"
              prop="port"
            >
              <el-input-number
                v-model="editForm.port"
                :min="1"
                :max="65535"
                controls-position="right"
              />
              <div class="form-tips">常用端口: SSL-993, 非SSL-143</div>
            </el-form-item>
            <el-form-item label="使用SSL" prop="use_ssl">
              <el-switch v-model="editForm.use_ssl" />
            </el-form-item>
          </template>
          <template v-if="editForm.mail_type === 'outlook'">
            <el-form-item label="Client ID" prop="client_id">
              <el-input v-model="editForm.client_id" />
            </el-form-item>
            <el-form-item label="Refresh Token" prop="refresh_token">
              <el-input v-model="editForm.refresh_token" />
            </el-form-item>
          </template>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="editDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="submitEditForm">确定</el-button>
          </span>
        </template>
      </el-dialog>

      <!-- 添加平台标签对话框 -->
      <el-dialog
        v-model="addPlatformDialogVisible"
        title="添加平台标签"
        width="400px"
        @close="resetPlatformForm"
      >
        <div v-if="currentPlatformEmail" class="platform-dialog-header">
          <p>邮箱: <strong>{{ currentPlatformEmail.email }}</strong></p>
        </div>
        <el-form :model="platformForm" label-width="80px">
          <el-form-item label="平台名称">
            <el-autocomplete
              v-model="platformForm.name"
              :fetch-suggestions="queryPlatformSuggestions"
              placeholder="输入平台名称，如: MoreLogin"
              clearable
              style="width: 100%"
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="addPlatformDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmAddPlatform" :loading="addingPlatform">确定</el-button>
          </span>
        </template>
      </el-dialog>

      <!-- 纠正平台名称对话框 -->
      <el-dialog
        v-model="correctPlatformDialogVisible"
        title="纠正平台名称"
        width="450px"
        @close="resetCorrectPlatformForm"
      >
        <div v-if="correctPlatformEmail" class="platform-dialog-header">
          <p>邮箱: <strong>{{ correctPlatformEmail.email }}</strong></p>
          <p>当前平台: <el-tag size="small">{{ correctPlatformForm.oldName }}</el-tag></p>
        </div>
        <el-form :model="correctPlatformForm" label-width="100px" style="margin-top: 16px;">
          <el-form-item label="正确名称">
            <el-autocomplete
              v-model="correctPlatformForm.newName"
              :fetch-suggestions="queryPlatformSuggestions"
              placeholder="输入正确的平台名称"
              clearable
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="记住纠正">
            <el-checkbox v-model="correctPlatformForm.remember">
              下次自动使用此名称（基于发件人域名）
            </el-checkbox>
          </el-form-item>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="correctPlatformDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmCorrectPlatform" :loading="correctingPlatform">确定</el-button>
          </span>
        </template>
      </el-dialog>

      <!-- 重命名平台对话框 -->
      <el-dialog
        v-model="renamePlatformDialogVisible"
        title="重命名平台"
        width="450px"
      >
        <p style="margin-bottom: 16px; color: #909399;">批量修改所有使用该平台名的邮箱</p>
        <el-form :model="renamePlatformForm" label-width="100px">
          <el-form-item label="原平台名">
            <el-select v-model="renamePlatformForm.oldName" placeholder="选择要重命名的平台" style="width: 100%">
              <el-option
                v-for="p in allPlatforms"
                :key="p.platform_name"
                :label="`${p.platform_name} (${p.count}个邮箱)`"
                :value="p.platform_name"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="新平台名">
            <el-input v-model="renamePlatformForm.newName" placeholder="输入新的平台名称" />
          </el-form-item>
        </el-form>
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="renamePlatformDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmRenamePlatform" :loading="renamingPlatform">确定</el-button>
          </span>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useEmailsStore } from '@/store/emails'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import {
  Delete,
  Refresh,
  Plus,
  Download,
  Document,
  Message,
  View,
  Hide,
  InfoFilled,
  CopyDocument,
  WarningFilled,
  Edit,
  Search
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'
import EmailContentViewer from '@/components/EmailContentViewer.vue'
import EmailAttachments from '@/components/EmailAttachments.vue'
import EmailQuoteFormatter from '@/components/EmailQuoteFormatter.vue'

const emailsStore = useEmailsStore()

// 列宽配置，从 localStorage 读取或使用默认值
const COLUMN_WIDTHS_KEY = 'emails_table_column_widths'
const defaultColumnWidths = {
  email: 220,
  mail_type: 120,
  password: 150,
  config: 200,
  platforms: 200,
  last_check_time: 180,
  actions: 360
}

const loadColumnWidths = () => {
  try {
    const saved = localStorage.getItem(COLUMN_WIDTHS_KEY)
    if (saved) {
      return { ...defaultColumnWidths, ...JSON.parse(saved) }
    }
  } catch (e) {
    console.error('加载列宽配置失败:', e)
  }
  return { ...defaultColumnWidths }
}

const columnWidths = reactive(loadColumnWidths())

// 列宽拖动结束时保存
const handleHeaderDragend = (newWidth, oldWidth, column) => {
  // 根据列的 label 映射到 prop
  const labelToProp = {
    '邮箱地址': 'email',
    '邮箱类型': 'mail_type',
    '密码': 'password',
    '配置信息': 'config',
    '已注册平台': 'platforms',
    '最后检查时间': 'last_check_time',
    '操作': 'actions'
  }
  const prop = column.property || labelToProp[column.label]
  if (prop && columnWidths[prop] !== undefined) {
    columnWidths[prop] = newWidth
    saveColumnWidths()
  }
}

const saveColumnWidths = () => {
  try {
    localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(columnWidths))
  } catch (e) {
    console.error('保存列宽配置失败:', e)
  }
}

// 状态
const loadingMails = ref(false)
const addEmailDialogVisible = ref(false)
const addEmailActiveTab = ref('single')
const mailContentDialogVisible = ref(false)
const mailListDialogVisible = ref(false)
const addingEmail = ref(false)
const importing = ref(false)

// 平台标签相关状态
const addPlatformDialogVisible = ref(false)
const currentPlatformEmail = ref(null)
const platformForm = ref({ name: '' })
const addingPlatform = ref(false)
const allPlatforms = ref([])  // 所有已使用的平台列表
const filterPlatform = ref('')  // 当前筛选的平台
const filterPlatformMode = ref('has')  // 筛选模式: has=已注册, not=未注册
const emailSearchFilter = ref('')  // 邮箱搜索过滤

// 纠正平台相关状态
const correctPlatformDialogVisible = ref(false)
const correctPlatformEmail = ref(null)
const correctPlatformForm = ref({ oldName: '', newName: '', remember: true, sender: '' })
const correctingPlatform = ref(false)

// 重命名平台相关状态
const renamePlatformDialogVisible = ref(false)
const renamePlatformForm = ref({ oldName: '', newName: '' })
const renamingPlatform = ref(false)

// 全局 Graph API 开关状态
const globalUseGraphApi = ref(false)
const outlookEmailCount = ref(0)
const subscriptionCount = ref(0)
const expiredCount = ref(0)
const creatingSubscriptions = ref(false)
const batchCheckingUnchecked = ref(false)

// 从服务器加载 Graph API 配置
const loadGraphApiConfig = async () => {
  try {
    const response = await fetch('/api/config/graph_api', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    if (response.ok) {
      const data = await response.json()
      globalUseGraphApi.value = data.use_graph_api
      outlookEmailCount.value = data.outlook_email_count || 0
      subscriptionCount.value = data.subscription_count || 0
      expiredCount.value = data.expired_count || 0
    }
  } catch (error) {
    console.error('加载 Graph API 配置失败:', error)
  }
}

// 为未订阅的邮箱创建订阅
const createMissingSubscriptions = async () => {
  creatingSubscriptions.value = true
  try {
    const response = await fetch('/api/graph/subscriptions/create_all', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ async: true })
    })
    
    if (response.ok) {
      ElMessage.success('正在后台创建订阅，请稍后刷新查看')
      // 延迟刷新统计
      setTimeout(() => {
        loadGraphApiConfig()
      }, 5000)
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '创建订阅失败')
    }
  } catch (error) {
    console.error('创建订阅失败:', error)
    ElMessage.error('创建订阅失败: ' + error.message)
  } finally {
    creatingSubscriptions.value = false
  }
}

// 添加邮箱表单引用
const addEmailFormRef = ref(null)
const batchImportFormRef = ref(null)

// 邮箱类型配置
const mailTypes = {
  outlook: {
    name: 'Outlook/Hotmail',
    color: 'primary'
  },
  imap: {
    name: 'IMAP邮箱',
    color: 'info'
  },
  gmail: {
    name: 'Gmail',
    color: 'danger'
  },
  qq: {
    name: 'QQ邮箱',
    color: 'success'
  }
}

// 获取邮箱类型名称
const getMailTypeName = (type) => {
  return mailTypes[type]?.name || type
}

// 获取邮箱类型颜色
const getMailTypeColor = (type) => {
  return mailTypes[type]?.color || 'default'
}

// 添加邮箱表单
const addEmailForm = ref({
  mail_type: 'outlook',
  email: '',
  password: '',
  client_id: '',
  refresh_token: '',
  server: '',
  port: 993,
  use_ssl: true
})

// 批量导入数据
const batchImport = reactive({
  data: '',
  mailType: 'outlook'
})

// 批量导入验证规则
const batchImportRules = {
  data: [
    { required: true, message: '导入数据不能为空', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (!value) {
          callback()
          return
        }

        const lines = value.trim().split('\n')
        let hasError = false

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim()
          if (!line) continue

          // 根据不同邮箱类型进行不同的验证
          if (batchImport.mailType === 'outlook') {
            const parts = line.split('----')
            if (parts.length !== 4) {
              hasError = true
              callback(new Error(`第 ${i + 1} 行格式错误，请使用"----"分隔邮箱、密码、客户端ID和RefreshToken`))
              break
            }

            if (!parts[0] || !parts[1] || !parts[2] || !parts[3]) {
              hasError = true
              callback(new Error(`第 ${i + 1} 行有空白字段，所有字段都必须填写`))
              break
            }

            // 简单的邮箱格式检查
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(parts[0])) {
              hasError = true
              callback(new Error(`第 ${i + 1} 行邮箱格式不正确`))
              break
            }
          }
        }

        if (!hasError) {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

// 添加邮箱表单验证规则
const addEmailRules = {
  mail_type: [{ required: true, message: '请选择邮箱类型', trigger: 'change' }],
  email: [{ required: true, message: '请输入邮箱地址', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  client_id: [{ required: true, message: '请输入Client ID', trigger: 'blur', validator: (rule, value, callback) => {
    if (addEmailForm.value.mail_type === 'outlook' && !value) {
      callback(new Error('请输入Client ID'))
    } else {
      callback()
    }
  }}],
  refresh_token: [{ required: true, message: '请输入Refresh Token', trigger: 'blur', validator: (rule, value, callback) => {
    if (addEmailForm.value.mail_type === 'outlook' && !value) {
      callback(new Error('请输入Refresh Token'))
    } else {
      callback()
    }
  }}],
  server: [{ required: true, message: '请输入服务器地址', trigger: 'blur', validator: (rule, value, callback) => {
    if (addEmailForm.value.mail_type === 'imap' && !value) {
      callback(new Error('请输入服务器地址'))
    } else {
      callback()
    }
  }}],
  port: [{ required: true, message: '请输入端口号', trigger: 'blur' }]
}

const selectedMail = ref(null)

// 计算属性
const emails = computed(() => emailsStore.emails)
const loading = computed(() => emailsStore.loading)
const currentEmail = computed(() => emailsStore.getEmailById(emailsStore.currentEmailId))
const mailRecords = computed(() => emailsStore.currentMailRecords)
const hasSelectedEmails = computed(() => emailsStore.hasSelectedEmails)
const selectedEmailsCount = computed(() => emailsStore.selectedEmailsCount)

// 根据平台筛选后的邮箱列表
const filteredEmails = computed(() => {
  let result = emails.value
  
  // 先按邮箱前缀过滤
  if (emailSearchFilter.value) {
    const searchLower = emailSearchFilter.value.toLowerCase()
    result = result.filter(email => 
      email.email && email.email.toLowerCase().startsWith(searchLower)
    )
  }
  
  // 如果没有选择平台，返回搜索结果
  if (!filterPlatform.value) {
    return result
  }
  
  // 筛选特定平台（不区分大小写）
  const filterLower = filterPlatform.value.toLowerCase()
  
  result = result.filter(email => {
    const platforms = email.platforms || []
    const hasPlatform = platforms.some(p => p && p.toLowerCase() === filterLower)
    
    if (filterPlatformMode.value === 'has') {
      return hasPlatform
    } else {
      return !hasPlatform
    }
  })
  
  return result
})

// 异常邮箱数量
const errorEmailCount = computed(() => {
  return emails.value.filter(email => email.last_error).length
})

// 方法
const refreshEmails = async () => {
  try {
    await emailsStore.fetchEmails()
    await loadAllPlatforms()  // 刷新时也加载平台列表
    ElMessage.success('刷新成功')
  } catch (error) {
    console.error('获取邮箱列表失败:', error)
    ElMessage.error('获取邮箱列表失败，请检查网络连接')
  }
}

const handleSelectionChange = (selection) => {
  if (Array.isArray(selection)) {
    emailsStore.selectedEmails = selection.map(item => item.id)
  } else {
    emailsStore.selectedEmails = []
  }
}

const handleDelete = (row) => {
  ElMessageBox.confirm(
    `确定要删除邮箱 ${row.email} 吗？`,
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await emailsStore.deleteEmail(row.id)
      ElMessage.success('删除成功')
    } catch (error) {
      console.error('删除邮箱失败:', error)
      ElMessage.error('删除邮箱失败: ' + (error.message || '未知错误'))
    }
  }).catch(() => {
    // 取消删除，不做任何操作
  })
}

const handleBatchDelete = () => {
  if (!hasSelectedEmails.value) {
    ElMessage.warning('请先选择要删除的邮箱')
    return
  }

  const count = emailsStore.selectedEmailsCount
  // 确保是数组并且创建副本
  const emailIds = Array.isArray(emailsStore.selectedEmails) ?
    [...emailsStore.selectedEmails] : []

  if (emailIds.length === 0) {
    ElMessage.warning('没有选中有效的邮箱')
    return
  }

  ElMessageBox.confirm(
    `确定要删除选中的 ${count} 个邮箱吗？`,
    '批量删除确认',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await emailsStore.deleteEmails(emailIds)
      ElMessage.success(`已成功删除 ${count} 个邮箱`)
    } catch (error) {
      console.error('批量删除邮箱失败:', error)
      ElMessage.error('批量删除邮箱失败: ' + (error.message || '未知错误'))
    }
  }).catch(() => {
    // 取消删除，不做任何操作
  })
}

const handleCheck = async (row) => {
  try {
    // 服务器会自动读取全局 Graph API 设置
    const result = await emailsStore.checkEmail(row.id)

    // 检查结果，确定是否显示正在处理中的消息
    if (result && result.status === 'processing') {
      ElMessage.warning(result.message || '邮箱正在处理中，请稍候...')
    } else {
      ElMessage.info(`正在检查邮箱 ${row.email} 的邮件，请稍候...`)
    }
  } catch (error) {
    console.error('检查邮箱失败:', error)
    ElMessage.error('检查邮箱失败: ' + (error.message || '未知错误'))
  }
}

const handleBatchCheck = async () => {
  if (!hasSelectedEmails.value) {
    ElMessage.warning('请先选择要检查的邮箱')
    return
  }

  const count = emailsStore.selectedEmailsCount
  // 确保是数组并且创建副本
  const emailIds = Array.isArray(emailsStore.selectedEmails) ?
    [...emailsStore.selectedEmails] : []

  if (emailIds.length === 0) {
    ElMessage.warning('没有选中有效的邮箱')
    return
  }

  try {
    // 服务器会自动读取全局 Graph API 设置
    await emailsStore.checkEmails(emailIds)
    ElMessage.info(`正在检查 ${count} 个邮箱的邮件，请稍候...`)
  } catch (error) {
    console.error('批量检查邮箱失败:', error)
    ElMessage.error('批量检查邮箱失败: ' + (error.message || '未知错误'))
  }
}

// 批量检查未收信的邮箱
const handleBatchCheckUnchecked = async () => {
  batchCheckingUnchecked.value = true
  try {
    const response = await fetch('/api/emails/batch_check_unchecked', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      }
    })
    const data = await response.json()
    if (response.ok) {
      if (data.count > 0) {
        ElMessage.success(`正在检查 ${data.count} 个未收信的邮箱...`)
      } else {
        ElMessage.info('没有未收信的邮箱')
      }
    } else {
      ElMessage.error(data.error || '操作失败')
    }
  } catch (error) {
    console.error('批量检查未收信邮箱失败:', error)
    ElMessage.error('操作失败: ' + (error.message || '未知错误'))
  } finally {
    batchCheckingUnchecked.value = false
  }
}

const handleViewMails = async (row) => {
  loadingMails.value = true
  try {
    emailsStore.currentEmailId = row.id
    await emailsStore.fetchMailRecords(row.id)
    mailListDialogVisible.value = true
  } catch (error) {
    console.error('获取邮件记录失败:', error)
    ElMessage.error('获取邮件记录失败: ' + (error.message || '未知错误'))
  } finally {
    loadingMails.value = false
  }
}

const viewMailContent = (mail) => {
  // 增加防护检查，确保mail对象及其必要字段存在
  if (!mail) {
    ElMessage.warning('邮件数据不存在或格式错误');
    return;
  }

  // 创建一个格式化后的副本，防止直接修改原始数据
  const formattedMail = {
    ...mail,
    subject: mail.subject || '(无主题)',
    sender: mail.sender || '(未知发件人)',
    received_time: mail.received_time || new Date().toISOString(),
    content: mail.content || '(无内容)'
  };

  selectedMail.value = formattedMail;
  mailContentDialogVisible.value = true;
}

const showAddEmailDialog = () => {
  resetAddEmailForm()
  addEmailDialogVisible.value = true
  addEmailActiveTab.value = 'single'
}

const handleAddOrImport = async () => {
  if (addEmailActiveTab.value === 'single') {
    await handleAddEmail()
  } else {
    await handleImport()
  }
}

const handleAddEmail = async () => {
  if (!addEmailFormRef.value) return

  try {
    // 表单验证
    await addEmailFormRef.value.validate()

    addingEmail.value = true
    const loading = ElLoading.service({
      lock: true,
      text: '正在添加邮箱...',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    const formData = {
      email: addEmailForm.value.email,
      password: addEmailForm.value.password,
      mail_type: addEmailForm.value.mail_type
    }

    if (addEmailForm.value.mail_type === 'outlook') {
      formData.client_id = addEmailForm.value.client_id
      formData.refresh_token = addEmailForm.value.refresh_token
    } else if (addEmailForm.value.mail_type === 'imap') {
      formData.server = addEmailForm.value.server
      formData.port = addEmailForm.value.port
      formData.use_ssl = addEmailForm.value.use_ssl
    }

    await emailsStore.addEmail(formData)
    addEmailDialogVisible.value = false
    ElMessage.success('添加邮箱成功')

    // 刷新邮箱列表
    await refreshEmails()
  } catch (error) {
    console.error('添加邮箱失败:', error)
    ElMessage.error('添加邮箱失败: ' + (error.message || '未知错误'))
  } finally {
    addingEmail.value = false
    ElLoading.service().close()
  }
}

const handleImport = async () => {
  if (!batchImportFormRef.value) return

  try {
    await batchImportFormRef.value.validate()

    importing.value = true

    const importData = {
      data: batchImport.data.trim(),
      mail_type: batchImport.mailType
    }

    await emailsStore.importEmails(importData)
    ElMessage.info('正在处理导入请求，请稍候...')

    // 延迟刷新列表
    setTimeout(async () => {
      await refreshEmails()
      ElMessage.success('批量导入完成')
      addEmailDialogVisible.value = false
    }, 2000)
  } catch (error) {
    console.error('导入邮箱失败:', error)
    ElMessage.error('导入邮箱失败: ' + (error.message || '未知错误'))
  } finally {
    importing.value = false
  }
}

const resetAddEmailForm = () => {
  addEmailForm.value = {
    mail_type: 'outlook',
    email: '',
    password: '',
    client_id: '',
    refresh_token: '',
    server: '',
    port: 993,
    use_ssl: true
  }
}

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '无';
  return dayjs(dateString).format('MM-DD HH:mm');
};

// 判断邮箱是否正在处理中
const isEmailProcessing = (email) => {
  const status = emailsStore.getProcessingStatus(email.id)
  return status && status.progress >= 0 && status.progress < 100
}

// 获取邮箱操作文本
const getEmailActionText = (email) => {
  return isEmailProcessing(email) ? '检查中...' : '检查邮件'
}

// 复制邮箱地址
const copyEmail = async (email) => {
  try {
    await navigator.clipboard.writeText(email)
    ElMessage.success('已复制邮箱地址')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

const togglePasswordVisibility = async (row) => {
  // 如果已经显示密码，则隐藏
  if (row.showPassword) {
    row.showPassword = false;
    return;
  }

  // 否则，从后端获取密码
  if (!row.password || row.password === '******') {
    row.passwordLoading = true;
    try {
      const response = await emailsStore.getEmailPassword(row.id);
      if (response && response.password) {
        row.password = response.password;
      }
    } catch (error) {
      console.error('获取密码失败:', error);
      ElMessage.error('获取密码失败: ' + (error.message || '未知错误'));
    } finally {
      row.passwordLoading = false;
    }
  }

  // 显示密码
  row.showPassword = true;
}

// 全局 Graph API 开关变更处理
const handleGlobalGraphApiChange = async (value) => {
  try {
    const response = await fetch('/api/graph/config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({ use_graph_api: value })
    })
    
    if (response.ok) {
      const mode = value ? 'Graph API' : 'IMAP';
      ElMessage.success(`已全局切换为 ${mode} 模式，所有 Outlook 邮箱将使用此模式`);
    } else {
      // 恢复原值
      globalUseGraphApi.value = !value
      ElMessage.error('设置失败，请重试')
    }
  } catch (error) {
    console.error('设置 Graph API 配置失败:', error)
    globalUseGraphApi.value = !value
    ElMessage.error('设置失败: ' + (error.message || '网络错误'))
  }
}

// 导出全部邮箱
const exportAllEmails = async () => {
  try {
    const response = await fetch('/api/emails/export', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    
    if (!response.ok) {
      ElMessage.error('导出失败')
      return
    }
    
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `emails_all_${new Date().toISOString().slice(0, 10)}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    
    ElMessage.success('导出成功')
  } catch (error) {
    console.error('导出邮箱失败:', error)
    ElMessage.error('导出失败: ' + (error.message || '网络错误'))
  }
}

// 导出筛选后的邮箱（只导出邮箱地址，每行一个）
const exportFilteredEmails = () => {
  if (!filterPlatform.value) {
    ElMessage.warning('请先选择平台')
    return
  }
  
  const emailList = filteredEmails.value.map(e => e.email)
  if (emailList.length === 0) {
    ElMessage.warning('没有符合条件的邮箱')
    return
  }
  
  const content = emailList.join('\n')
  const blob = new Blob([content], { type: 'text/plain' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  
  // 生成文件名：平台名_已注册/未注册_日期.txt
  const status = filterPlatformMode.value === 'has' ? 'registered' : 'unregistered'
  const filename = `${filterPlatform.value}_${status}_${new Date().toISOString().slice(0, 10)}.txt`
  
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
  
  ElMessage.success(`已导出 ${emailList.length} 个邮箱`)
}

// 清除异常邮箱
const clearErrorEmails = async () => {
  const errorEmails = emails.value.filter(e => e.last_error)
  if (errorEmails.length === 0) {
    ElMessage.info('没有异常邮箱')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除 ${errorEmails.length} 个异常邮箱吗？此操作不可恢复！`,
      '警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const loading = ElLoading.service({ text: '正在删除异常邮箱...' })
    
    let successCount = 0
    let failCount = 0
    
    for (const email of errorEmails) {
      try {
        const response = await fetch(`/api/emails/${email.id}`, {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        })
        if (response.ok) {
          successCount++
        } else {
          failCount++
        }
      } catch {
        failCount++
      }
    }
    
    loading.close()
    
    if (successCount > 0) {
      ElMessage.success(`成功删除 ${successCount} 个异常邮箱`)
      await emailsStore.fetchEmails()
    }
    if (failCount > 0) {
      ElMessage.warning(`${failCount} 个邮箱删除失败`)
    }
  } catch {
    // 用户取消
  }
}

// 检查邮件内容是否为HTML格式
const isHtmlContent = (mail) => {
  if (!mail || !mail.content) return false;

  // 兼容新旧格式
  if (typeof mail.content === 'object') {
    return mail.content.has_html === true || mail.content.content_type === 'text/html';
  }

  // 旧格式，检查内容是否包含HTML标签
  const content = String(mail.content);
  return content.includes('<html') || content.includes('<body') ||
         content.includes('<div') || content.includes('<p>') ||
         content.includes('<table') || content.includes('<img');
}

// 获取邮件内容
const getMailContent = (mail) => {
  if (!mail) return '';

  // 兼容新旧格式
  if (typeof mail.content === 'object' && mail.content !== null) {
    return mail.content.content || '';
  }

  return mail.content || '';
}

// 截断内容
const truncateContent = (content) => {
  if (!content) return content;

  const maxLength = 1000; // 设置最大长度
  if (content.length > maxLength) {
    return content.slice(0, maxLength) + '...';
  }
  return content;
}

// 净化HTML内容，防止XSS攻击
const sanitizeHtml = (html) => {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a', 'b', 'br', 'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'i', 'img', 'li', 'ol', 'p', 'span', 'strong', 'table', 'tbody',
      'td', 'th', 'thead', 'tr', 'u', 'ul', 'font', 'blockquote', 'hr',
      'pre', 'code', 'col', 'colgroup', 'section', 'header', 'footer',
      'nav', 'article', 'aside', 'figure', 'figcaption', 'address', 'main',
      'caption', 'center', 'cite', 'dd', 'dl', 'dt', 'mark', 's', 'small',
      'strike', 'sub', 'sup'
    ],
    ALLOWED_ATTR: [
      'href', 'target', 'src', 'alt', 'style', 'class', 'id', 'width', 'height',
      'align', 'valign', 'bgcolor', 'border', 'cellpadding', 'cellspacing',
      'color', 'colspan', 'dir', 'face', 'frame', 'frameborder', 'headers',
      'hspace', 'lang', 'marginheight', 'marginwidth', 'nowrap', 'rel',
      'rev', 'rowspan', 'scrolling', 'shape', 'span', 'summary', 'title',
      'usemap', 'vspace', 'start', 'type', 'value', 'size', 'data-*'
    ]
  });
}

// 下载附件
const downloadAttachment = (attachmentId, filename) => {
  const token = localStorage.getItem('token')
  const downloadUrl = `/api/attachments/${attachmentId}/download`

  // 创建一个隐藏的a标签用于下载
  const link = document.createElement('a')
  link.href = downloadUrl
  link.setAttribute('download', filename)
  link.setAttribute('target', '_blank')

  // 添加认证头
  fetch(downloadUrl, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  })
  .then(response => response.blob())
  .then(blob => {
    const url = window.URL.createObjectURL(blob)
    link.href = url
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  })
  .catch(error => {
    console.error('下载附件失败:', error)
    ElMessage.error('下载附件失败')
  })
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 添加编辑按钮的处理函数
const handleEdit = (email) => {
  // 确保use_ssl是布尔值
  const emailData = { ...email }
  if (emailData.mail_type === 'imap') {
    emailData.use_ssl = Boolean(emailData.use_ssl)
  }
  editForm.value = emailData
  editDialogVisible.value = true
}

// 引用和定义编辑对话框相关变量
const editDialogVisible = ref(false)
const editFormRef = ref(null)
const editForm = ref({
  id: null,
  email: '',
  password: '',
  mail_type: 'outlook',
  server: '',
  port: 993,
  use_ssl: true,
  client_id: '',
  refresh_token: ''
})

// 密码强度相关
const passwordStrength = ref(0)
const passwordStrengthColor = computed(() => {
  if (passwordStrength.value < 40) return '#F56C6C'
  if (passwordStrength.value < 80) return '#E6A23C'
  return '#67C23A'
})

const passwordStrengthText = (percentage) => {
  if (percentage < 40) return '弱'
  if (percentage < 80) return '中'
  return '强'
}

const checkPasswordStrength = (password) => {
  if (!password) {
    passwordStrength.value = 0
    return
  }

  let strength = 0
  // 检查长度
  if (password.length >= 8) strength += 20
  // 检查是否包含数字
  if (/\d/.test(password)) strength += 20
  // 检查是否包含小写字母
  if (/[a-z]/.test(password)) strength += 20
  // 检查是否包含大写字母
  if (/[A-Z]/.test(password)) strength += 20
  // 检查是否包含特殊字符
  if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength += 20

  passwordStrength.value = strength
}

// 编辑表单的规则
const editRules = {
  email: [
    { required: true, message: '邮箱地址不能为空', trigger: 'blur' },
    { type: 'email', message: '邮箱地址格式不正确', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '密码不能为空', trigger: 'blur' },
    { min: 6, message: '密码长度不能小于6位', trigger: 'blur' }
  ],
  server: [
    { required: true, message: 'IMAP服务器地址不能为空', trigger: 'blur',
      // 仅当类型为imap时验证
      validator: (rule, value, callback) => {
        if (editForm.value.mail_type === 'imap' && !value) {
          callback(new Error('IMAP服务器地址不能为空'));
        } else {
          callback();
        }
      }
    }
  ],
  port: [
    {
      required: true,
      message: '端口号不能为空',
      trigger: 'blur',
      // 仅当类型为imap时验证
      validator: (rule, value, callback) => {
        if (editForm.value.mail_type === 'imap' && (!value || isNaN(value))) {
          callback(new Error('端口号必须是有效数字'));
        } else {
          callback();
        }
      }
    }
  ],
  client_id: [
    {
      required: true,
      message: 'Client ID不能为空',
      trigger: 'blur',
      // 仅当类型为outlook时验证
      validator: (rule, value, callback) => {
        if (editForm.value.mail_type === 'outlook' && !value) {
          callback(new Error('Client ID不能为空'));
        } else {
          callback();
        }
      }
    }
  ],
  refresh_token: [
    {
      required: true,
      message: 'Refresh Token不能为空',
      trigger: 'blur',
      // 仅当类型为outlook时验证
      validator: (rule, value, callback) => {
        if (editForm.value.mail_type === 'outlook' && !value) {
          callback(new Error('Refresh Token不能为空'));
        } else {
          callback();
        }
      }
    }
  ],
}

// 重置编辑表单
const resetEditForm = () => {
  editForm.value = {
    id: null,
    email: '',
    password: '******',  // 默认显示星号，实际修改时会获取真实密码
    mail_type: 'outlook',
    client_id: '',
    refresh_token: '',
    server: '',
    port: 993,
    use_ssl: true
  }
}

// 提交编辑表单
const submitEditForm = async () => {
  if (!editFormRef.value) return

  try {
    await editFormRef.value.validate()

    // 准备提交的数据
    const formData = { ...editForm.value }

    // 如果密码仍然是默认的星号，则不发送密码更新
    if (formData.password === '******') {
      delete formData.password
    }

    const loading = ElLoading.service({
      lock: true,
      text: '正在更新邮箱...',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    await emailsStore.updateEmail(formData.id, formData)
    editDialogVisible.value = false

    // 刷新邮箱列表
    await refreshEmails()

    ElMessage.success('邮箱更新成功')
  } catch (error) {
    console.error('更新邮箱失败:', error)
    ElMessage.error('更新邮箱失败: ' + (error.message || '未知错误'))
  } finally {
    ElLoading.service().close()
  }
}

// ==================== 平台标签相关方法 ====================

// 加载所有已使用的平台列表
const loadAllPlatforms = async () => {
  try {
    const response = await fetch('/api/platforms', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    if (response.ok) {
      allPlatforms.value = await response.json()
    }
  } catch (error) {
    console.error('加载平台列表失败:', error)
  }
}

// 平台筛选变化
const handlePlatformFilterChange = () => {
  // 清空选中状态
  emailsStore.selectedEmails = []
}

// 平台名称自动补全
const queryPlatformSuggestions = (queryString, cb) => {
  const results = queryString
    ? allPlatforms.value.filter(p => p.platform_name.toLowerCase().includes(queryString.toLowerCase()))
    : allPlatforms.value
  cb(results.map(p => ({ value: p.platform_name, count: p.count })))
}

// 显示添加平台对话框
const showAddPlatformDialog = (email) => {
  currentPlatformEmail.value = email
  platformForm.value.name = ''
  addPlatformDialogVisible.value = true
}

// 重置平台表单
const resetPlatformForm = () => {
  platformForm.value.name = ''
  currentPlatformEmail.value = null
}

// 确认添加平台标签
const confirmAddPlatform = async () => {
  if (!platformForm.value.name.trim()) {
    ElMessage.warning('请输入平台名称')
    return
  }
  
  addingPlatform.value = true
  try {
    const response = await fetch(`/api/emails/${currentPlatformEmail.value.id}/platforms`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ platform_name: platformForm.value.name.trim() })
    })
    
    if (response.ok) {
      ElMessage.success('添加成功')
      addPlatformDialogVisible.value = false
      // 刷新邮箱列表
      await emailsStore.fetchEmails()
      await loadAllPlatforms()
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '添加失败')
    }
  } catch (error) {
    console.error('添加平台标签失败:', error)
    ElMessage.error('添加失败: ' + error.message)
  } finally {
    addingPlatform.value = false
  }
}

// 移除平台标签
const removePlatform = async (emailId, platformName) => {
  try {
    const response = await fetch(`/api/emails/${emailId}/platforms/${encodeURIComponent(platformName)}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    
    if (response.ok) {
      ElMessage.success('移除成功')
      // 刷新邮箱列表
      await emailsStore.fetchEmails()
      await loadAllPlatforms()
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '移除失败')
    }
  } catch (error) {
    console.error('移除平台标签失败:', error)
    ElMessage.error('移除失败: ' + error.message)
  }
}

// 显示纠正平台对话框
const showCorrectPlatformDialog = (email, platformName) => {
  correctPlatformEmail.value = email
  correctPlatformForm.value = {
    oldName: platformName,
    newName: platformName,
    remember: true,
    sender: ''  // 需要从最近邮件获取发件人
  }
  correctPlatformDialogVisible.value = true
}

// 重置纠正平台表单
const resetCorrectPlatformForm = () => {
  correctPlatformEmail.value = null
  correctPlatformForm.value = { oldName: '', newName: '', remember: true, sender: '' }
}

// 确认纠正平台名称
const confirmCorrectPlatform = async () => {
  if (!correctPlatformForm.value.newName.trim()) {
    ElMessage.warning('请输入正确的平台名称')
    return
  }
  
  if (correctPlatformForm.value.newName.trim() === correctPlatformForm.value.oldName) {
    ElMessage.warning('新名称与原名称相同')
    return
  }
  
  correctingPlatform.value = true
  try {
    const response = await fetch(`/api/emails/${correctPlatformEmail.value.id}/correct_platform`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        old_name: correctPlatformForm.value.oldName,
        new_name: correctPlatformForm.value.newName.trim(),
        // 如果勾选了记住，传入发件人域名（这里简化处理，使用邮箱域名）
        sender: correctPlatformForm.value.remember ? `@${correctPlatformForm.value.oldName.toLowerCase()}.com` : null
      })
    })
    
    if (response.ok) {
      ElMessage.success('纠正成功')
      correctPlatformDialogVisible.value = false
      await emailsStore.fetchEmails()
      await loadAllPlatforms()
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '纠正失败')
    }
  } catch (error) {
    console.error('纠正平台名称失败:', error)
    ElMessage.error('纠正失败: ' + error.message)
  } finally {
    correctingPlatform.value = false
  }
}

// 显示重命名平台对话框
const showRenamePlatformDialog = () => {
  renamePlatformForm.value = { oldName: '', newName: '' }
  renamePlatformDialogVisible.value = true
}

// 确认重命名平台
const confirmRenamePlatform = async () => {
  if (!renamePlatformForm.value.oldName || !renamePlatformForm.value.newName.trim()) {
    ElMessage.warning('请选择平台并输入新名称')
    return
  }
  
  if (renamePlatformForm.value.oldName === renamePlatformForm.value.newName.trim()) {
    ElMessage.warning('新名称与原名称相同')
    return
  }
  
  renamingPlatform.value = true
  try {
    const response = await fetch('/api/platforms/rename', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        old_name: renamePlatformForm.value.oldName,
        new_name: renamePlatformForm.value.newName.trim()
      })
    })
    
    if (response.ok) {
      const data = await response.json()
      ElMessage.success(data.message || '重命名成功')
      renamePlatformDialogVisible.value = false
      await emailsStore.fetchEmails()
      await loadAllPlatforms()
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '重命名失败')
    }
  } catch (error) {
    console.error('重命名平台失败:', error)
    ElMessage.error('重命名失败: ' + error.message)
  } finally {
    renamingPlatform.value = false
  }
}

// 生命周期钩子
onMounted(() => {
  emailsStore.initWebSocketListeners()
  refreshEmails()
  loadGraphApiConfig()  // 加载 Graph API 配置
  loadAllPlatforms()    // 加载平台列表
})
</script>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--bg-color);
  overflow-x: hidden;
}

.emails-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
  width: 100%;
}

.email-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.email-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.email-text.email-error {
  color: #f56c6c;
  font-weight: 500;
}

.error-icon {
  color: #f56c6c;
  margin-right: 4px;
  cursor: help;
  flex-shrink: 0;
}

.error-info {
  max-width: 100%;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  cursor: help;
}

.platforms-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.platform-tag {
  margin: 0;
}

.platform-tag.clickable {
  cursor: pointer;
  transition: all 0.2s;
}

.platform-tag.clickable:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.add-platform-btn {
  padding: 2px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.add-platform-btn:hover {
  opacity: 1;
}

.platform-dialog-header {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.platform-dialog-header p {
  margin: 0;
}

.platform-filter {
  flex-shrink: 0;
}

.copy-btn {
  flex-shrink: 0;
  padding: 2px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.copy-btn:hover {
  opacity: 1;
}

.email-list-card {
  margin: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
  transition: all var(--transition-normal);
}

.card-header {
  width: 100%;
}

.page-title {
  font-size: 1.5rem;
  color: var(--primary-color);
  margin: 0;
  position: relative;
  display: inline-block;
}

.page-title::after {
  content: '';
  position: absolute;
  bottom: -5px;
  left: 0;
  width: 40px;
  height: 3px;
  background-color: var(--primary-color);
  border-radius: 999px;
}

.email-table {
  border-radius: var(--border-radius);
  overflow: hidden;
}

.mail-type-tag {
  font-weight: 500;
}

.password-field {
  width: 100%;
}

.password-text {
  font-family: monospace;
}

.password-toggle-btn:hover {
  transform: scale(1.1);
}

.time-field {
  color: var(--secondary-text-color);
  font-size: 0.9rem;
}

.progress-container {
  width: 100%;
  padding: 0 5px;
}

.progress-message {
  font-size: 0.8rem;
  margin-top: 4px;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  justify-content: space-around;
}

.action-btn {
  min-width: 70px;
  margin: 2px;
  white-space: nowrap;
}

.mail-dialog-header {
  padding: 0 0 10px 0;
  border-bottom: 1px solid var(--border-color-light);
}

.email-title {
  font-size: 1.2rem;
  margin: 0;
}

.mail-list-table {
  border-radius: var(--border-radius);
  overflow: hidden;
}

.subject-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.mail-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mail-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-item {
  width: 100%;
}

.label {
  font-weight: 500;
  margin-right: 10px;
}

.mail-content {
  max-height: 400px;
  overflow-y: auto;
}

.mail-attachments {
  margin: 10px 0;
  padding: 10px;
  background-color: #f0f9eb;
  border-radius: 4px;
  border-left: 3px solid #67c23a;
}

.attachments-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}

.attachment-item {
  margin-bottom: 5px;
}

.mail-content-text {
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  max-width: 100%;
  font-family: monospace;
  font-size: 0.9rem;
  line-height: 1.5;
  padding: 10px;
  background-color: var(--bg-light);
  border-radius: var(--border-radius);
}

.html-content {
  max-width: 100%;
  overflow-x: auto;
  padding: 10px;
  background-color: var(--bg-light);
  border-radius: var(--border-radius);
  line-height: 1.5;
}

.html-content img {
  max-width: 100%;
  height: auto;
}

.html-content a {
  color: var(--primary-color);
  text-decoration: underline;
}

.html-content table {
  border-collapse: collapse;
  margin: 10px 0;
}

.html-content th,
.html-content td {
  border: 1px solid #ddd;
  padding: 8px;
}

.add-email-form {
  padding: 20px;
}

.w-full {
  width: 100%;
}

.import-help {
  margin-bottom: 20px;
  padding: 10px;
  background-color: var(--bg-light);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
  line-height: 1.5;
}

.server-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}

.server-field, .port-field, .config-info {
  color: var(--secondary-text-color);
}

.config-info {
  font-style: italic;
  font-size: 0.85rem;
}

.flex {
  display: flex;
  align-items: center;
}

.flex-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gap-sm {
  gap: 8px;
}

.gap-md {
  gap: 16px;
}

.mb-4 {
  margin-bottom: 16px;
}

.text-center {
  text-align: center;
}

.text-primary {
  color: var(--primary-color);
}

.hover-scale {
  transition: transform 0.2s;
}

.hover-scale:hover:not(:disabled) {
  transform: scale(1.05);
}
</style>