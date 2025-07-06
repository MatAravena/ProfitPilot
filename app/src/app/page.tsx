import { Container } from "@components/Container";
import { Landing } from "@components/Landing";
import { SectionTitle } from "@components/SectionTitle"; 
import { Benefits } from "@components/Benefits";
import { benefitOne, benefitTwo } from "./components/data";
import { Video } from "@components/Video";
import { Cta } from "@components/Cta";
import { Faq } from "@components/Faq";
import { Testimonials } from "@components/Testimonials";

export default function Home() {
  return ( 
  <Container>
      <Landing />
      <SectionTitle
        preTitle="Profit Pilot Benefits"
        title="Why should you give it a try?"
        widthChildren={'3'}
        texts={['Profit Pilot is designed to empower whether you are a seasoned investor or just starting out—by providing a smart, data-driven way to grow your wealth effortlessly.',
          'Our goal is to help users achieve a better financial future through a safe, passive income stream that is fully controlled by you and guided by cutting-edge technology.',
          'By eliminating emotional decision-making and human errors, Profit Pilot leverages AI, machine learning, and advanced trading algorithms to make investing easier, safer, and more effective.',
          'You stay in control while the technology works for you.',
        ]}
      />

      <Benefits data={benefitOne} />
      <Benefits imgPos="right" data={benefitTwo} />

      <SectionTitle
        preTitle="Watch a video"
        title="Learn how to fullfil your needs"
      >
        This section is to highlight a promo or demo video of your product.
        Analysts says a landing page with video has 3% more conversion rate. So,
        don&apos;t forget to add one. Just like this.
      </SectionTitle>

      <Video videoId="fZ0D0cnR88E" />

      <SectionTitle
        preTitle="Testimonials"
        title="Here's what our customers said"
      >
        Testimonials is a great way to increase the brand trust and awareness.
        Use this section to highlight your popular customers.
      </SectionTitle>

      <Testimonials />

      <SectionTitle preTitle="FAQ" title="Frequently Asked Questions">
        Answer your customers possible questions here, it will increase the
        conversion rate as well as support or chat requests.
      </SectionTitle>

      <Faq />
      <Cta />
  </Container>
  )
}

{/* <div className="grid grid-rows-[20px_1fr_20px] items-center justify-items-center min-h-screen p-8 pb-20 gap-16 sm:p-20 font-[family-name:var(--font-geist-sans)]">
  <main className="flex flex-col gap-8 row-start-2 items-center sm:items-start">
    <Image
      className="dark:invert"
      src="/next.svg"
      alt="Next.js logo"
      width={180}
      height={38}
      priority
    />
    <ol className="list-inside list-decimal text-sm text-center sm:text-left font-[family-name:var(--font-geist-mono)]">
      <li className="mb-2">
        Get started by editing{" "}
        <code className="bg-black/[.05] dark:bg-white/[.06] px-1 py-0.5 rounded font-semibold">
          src/app/page.tsx
        </code>
        .
      </li>
      <li>Save and see your changes instantly.</li>
      <Greet/>
      <br />
      <Counter/>
    </ol>  

    <div className="flex gap-4 items-center flex-col sm:flex-row">
      <a
        className="rounded-full border border-solid border-transparent transition-colors flex items-center justify-center bg-foreground text-background gap-2 hover:bg-[#383838] dark:hover:bg-[#ccc] text-sm sm:text-base h-10 sm:h-12 px-4 sm:px-5"
        href="https://vercel.com/new?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        target="_blank"
        rel="noopener noreferrer"
      >
        <Image
          className="dark:invert"
          src="/vercel.svg"
          alt="Vercel logomark"
          width={20}
          height={20}
        />
        Deploy now
      </a>
      <a
        className="rounded-full border border-solid border-black/[.08] dark:border-white/[.145] transition-colors flex items-center justify-center hover:bg-[#f2f2f2] dark:hover:bg-[#1a1a1a] hover:border-transparent text-sm sm:text-base h-10 sm:h-12 px-4 sm:px-5 sm:min-w-44"
        href="https://nextjs.org/docs?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        target="_blank"
        rel="noopener noreferrer"
      >
        Read our docs
      </a>
    </div>
  </main>
</div> */}