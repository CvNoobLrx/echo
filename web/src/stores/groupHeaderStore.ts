import { create } from 'zustand'
import type { MenuProps } from 'antd'

// 群聊页把「群聊列表 / 邀请 / 更多」操作注册到这里，
// 供 MainLayout 顶栏在手机端群聊页渲染（替代搜索框 + 替代群聊自己的标题栏），合并成一行。
interface GroupHeaderState {
  active: boolean // 当前是否在群聊页且已选中会话
  title?: string // 当前群名（顶栏展示）
  openList?: () => void // 打开群聊列表抽屉
  openInvite?: () => void // 打开邀请弹窗
  moreItems: MenuProps['items'] // 「更多」下拉菜单项（开新对话/清空/退群等）
  register: (actions: {
    title: string
    openList: () => void
    openInvite: () => void
    moreItems: MenuProps['items']
  }) => void
  clear: () => void
}

export const useGroupHeaderStore = create<GroupHeaderState>((set) => ({
  active: false,
  moreItems: [],
  register: ({ title, openList, openInvite, moreItems }) =>
    set({ active: true, title, openList, openInvite, moreItems }),
  clear: () =>
    set({
      active: false,
      title: undefined,
      openList: undefined,
      openInvite: undefined,
      moreItems: [],
    }),
}))
