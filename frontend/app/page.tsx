import { Header } from "@/components/Header";
import { UploadSection } from "@/components/UploadSection";

export default function Home() {
  return (
    <main className="bg-white flex flex-col items-center justify-center relative min-h-screen w-full">
      <Header />
      <UploadSection />
    </main>
  );
}