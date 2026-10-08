import { ReactNode } from "react";

export default async function Layout({
  children,
}: {
  children: ReactNode;
}): Promise<Element> {
  return (
    <div className="page-container">
      {children}
    </div>
  );
}
