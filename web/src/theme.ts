import type { ThemeConfig } from 'antd'

// Echo 使用中性工作台底色，仅用品牌蓝表示主要操作与选中状态。
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#175CD3',
    colorInfo: '#175CD3',
    colorSuccess: '#287A3D',
    colorWarning: '#A15C07',
    colorError: '#B42318',
    colorTextBase: '#202124',
    colorTextSecondary: '#5F6368',
    colorBorder: '#DADCE0',
    colorBorderSecondary: '#E8EAED',
    colorBgBase: '#FFFFFF',
    colorBgLayout: '#F6F7F8',
    borderRadius: 6,
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeSM: 12,
    lineHeight: 1.5715,
    controlHeight: 36,
    fontFamily:
      "'PingFang SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', sans-serif",
    boxShadowSecondary: '0 1px 2px rgba(32, 33, 36, 0.08), 0 4px 10px -6px rgba(32, 33, 36, 0.16)',
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: '#ffffff',
      headerHeight: 64,
      bodyBg: '#F6F7F8',
    },
    Menu: {
      itemBg: '#ffffff',
      itemSelectedBg: '#EAF1FB',
      itemSelectedColor: '#174EA6',
      itemHoverBg: '#F1F3F4',
      itemColor: '#3C4043',
      itemHeight: 38,
      itemMarginInline: 8,
      itemMarginBlock: 2,
      fontSize: 14,
      groupTitleColor: '#80868B',
      groupTitleFontSize: 12,
    },
    Card: {
      borderRadiusLG: 6,
    },
    Button: {
      controlHeight: 36,
      fontWeight: 500,
    },
    Input: {
      fontSize: 14,
    },
    Modal: {
      borderRadiusLG: 10,
      titleFontSize: 17,
      headerBg: '#ffffff',
      paddingMD: 24,
      paddingContentHorizontalLG: 24,
    },
  },
}
