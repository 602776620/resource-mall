import { useParams } from "react-router-dom";
import { Placeholder } from "@/components/Placeholder";

export function OrderPaymentPage() {
  const { orderNo } = useParams<{ orderNo: string }>();
  return <Placeholder title={`待支付 ${orderNo ?? ""}`} note="收款码 + 倒计时 + 状态轮询 + 我已付款（T06 实现）。" />;
}
