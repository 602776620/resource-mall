import { useParams } from "react-router-dom";
import { Placeholder } from "@/components/Placeholder";

export function AdminProductFormPage() {
  const { id } = useParams<{ id: string }>();
  const title = id ? `编辑资源 #${id}` : "新建资源";
  return <Placeholder title={title} note="标题/分类/价格/封面/预览/资源文件（T04 实现）。" />;
}
