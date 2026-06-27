# Inciting incident

You: Please invent an inside-out Haskell that has monads, lazy evaluation,
referential transparency, pure functions, and algebraic data types, but when
you want them. And doesn't make you want to pound your head on a desk

ChatGPT: Let’s call it Evert: Haskell turned inside-out, with the mathematical
machinery retained and the sharp edges folded safely into the engine room.

Its governing rule is:

> Power should be local, explicit, and non-contagious.

Evert is strict by default. Effects use ordinary direct-style code. The
compiler infers and tracks them. Pure functions remain referentially
transparent. Laziness appears only where you mark it. Monads are fully
supported, but they do not seize control of the entire program and demand a
tower of transformers as tribute.

```evert
pure fn greeting(name: Text) -> Text =
    "Hello, {name}!"

fn main() ! Console {
    let name = Console.ask("What is your name? ")
    Console.say(greeting(name))
}
```

`greeting` is provably pure. `main` performs the `Console` effect. Calling pure
code from effectful code works normally; calling effectful code from pure code
produces a compact, intelligible error:

```text
Console.ask performs the Console effect.
pure function greeting permits no effects.

Either:
  • move this operation into an effectful caller
  • add `! Console` and remove `pure`
  • handle Console locally
```

No seventeen-screen dissertation involving `RealWorld`, skolem variables, or a
type synonym you did not know existed.

## Strict until you ask otherwise

Normal expressions use eager, call-by-value evaluation:

```evert
let total = expensiveCalculation()   // evaluated now
```

Laziness is attached to a binding or field:

```evert
let lazy total = expensiveCalculation()  // evaluated on first use, once
```

A lazy expression must be pure. This avoids the traditional swamp of effects
whose timing depends on whether a value happened to be demanded:

```evert
let lazy line = Console.readLine()
```

```text
Cannot defer an effectful expression with `lazy`.

Lazy expressions may be evaluated later, once, or not at all.
Use `Task<Text>` for deferred effects.
```

Effectful deferral uses an explicit value:

```evert
let lineTask = task {
    Console.readLine()
}

let line = await lineTask
```

So Evert has both laziness and deferred effects, but refuses to pretend they
are the same creature wearing different hats.

Lazy fields make infinite structures pleasant:

```evert
data Stream<T> =
    End
  | Next(head: T, tail: lazy Stream<T>)

pure fn naturals(n: Int) -> Stream<Int> =
    Next(n, lazy naturals(n + 1))

pure fn squares() -> Stream<Int> =
    naturals(1).map(x => x * x)
```

Pattern matching forces only the part required to determine the constructor.
Lazy values use call-by-need and memoize their result.

## Purity is a contract, not a lifestyle mandate

Ordinary functions have inferred effects:

```evert
fn fetchUser(id: UserId) {
    let row = Database.query("select * from users where id = ?", id)
    Audit.record(UserFetched(id))
    decodeUser(row)
}
```

The compiler infers:

```evert
fn fetchUser(id: UserId) -> User
    ! { Database, Audit, Throw<DecodeError> }
```

For public APIs, Evert requires an explicit effect signature. Internal
functions may leave it inferred.

`pure` acts as a lock:

```evert
pure fn calculateTax(income: Money) -> Money {
    // The compiler guarantees an empty effect row.
}
```

Any expression with an empty effect row is referentially transparent, whether
or not the programmer wrote `pure`. The keyword exists to assert intent and
prevent future edits from quietly introducing effects.

Time, randomness, exceptions, environment variables, logging, mutation and
filesystem access all count as effects. None sneak through a side door labelled
“technically pure because unsafePerformIO”.

Function types carry effects too:

```evert
Text -> Int                       // pure
Text -> Int ! Throw<ParseError>   // effectful
```

Higher-order functions can remain effect-polymorphic:

```evert
fn map<A, B, E>(
    values: Vector<A>,
    transform: A -> B ! E
) -> Vector<B> ! E
```

## Monads when they clarify the problem

Evert has `Functor`, `Applicative`, `Monad`, higher-kinded type parameters and
lawful generic abstraction:

```evert
trait Monad<M<_>> {
    pure<T>(value: T) -> M<T>

    flatMap<A, B>(
        value: M<A>,
        next: A -> M<B>
    ) -> M<B>
}
```

It also has generic `do` notation:

```evert
pure fn findBillingEmail(
    users: Map<UserId, User>,
    id: UserId
) -> Option<Text> =
    do Option {
        user    <- users.get(id)
        account <- user.billingAccount
        email   <- account.email
        yield email
    }
```

For `Result`:

```evert
data InputError =
    MissingName
  | BadAge(Text)
  | TooYoung(Int)

data User = User {
    name: Text,
    age: Int
}

pure fn parseUser(
    nameText: Text,
    ageText: Text
) -> Result<User, InputError> =
    do Result {
        name <- nonBlank(nameText)
            .orErr(MissingName)

        age <- ageText
            .parse<Int>()
            .mapErr(_ => BadAge(ageText))

        ensure age >= 18 else TooYoung(age)

        yield User(name, age)
    }
```

Monads therefore remain useful for data-level sequencing: parsers, validation,
optional values, nondeterminism, state machines and domain-specific
computations.

Effects use direct style because the compiler lowers effectful functions into a
monadic intermediate representation. The monad is still there; it simply does
not insist on driving the car.

Monad transformers remain expressible, but ordinary programs use effect rows
and handlers instead. They can enjoy a quiet retirement beside manual vtables
and handwritten continuation-passing style.

## Algebraic effects instead of `IO` swallowing the world

Effects are declared like interfaces:

```evert
effect Console {
    ask(prompt: Text) -> Text
    say(message: Text) -> Unit
}

effect Clock {
    now() -> Instant
}
```

A function declares only what it needs:

```evert
fn greet() ! { Console, Clock } {
    let name = Console.ask("Name: ")
    let time = Clock.now()
    Console.say("[{time}] Hello, {name}.")
}
```

Handlers can interpret an effect:

```evert
let transcript =
    handle greet() with TestConsole {
        answers = ["Payton"]
    }
```

If the handler eliminates every effect, the whole expression becomes pure.
Tests can therefore run deterministic effectful programs without mocking global
state or threading an abstract `MonadConsoleClockDatabase m` constraint through
seventy-three unrelated functions.

Handlers may transform effects too:

```evert
handle operation() with {
    Database.query(q, args) =>
        Cache.lookup(q, args)
            .orElse(() => RealDatabase.query(q, args))
}
```

## Algebraic data types, naturally

Sum types and product types look unsurprising:

```evert
data Shape =
    Circle(radius: Float)
  | Rectangle(width: Float, height: Float)
  | Polygon(points: Vector<Point>)
```

Matches must be exhaustive:

```evert
pure fn area(shape: Shape) -> Float =
    match shape {
        Circle(r)       => pi * r²
        Rectangle(w, h) => w * h
        Polygon(points) => polygonArea(points)
    }
```

The compiler reports missing constructors directly:

```text
Non-exhaustive match on Shape.

Missing case:
    Polygon(_)
```

Records support immutable nested updates without summoning a lens ecosystem:

```evert
let moved =
    user with {
        address.city = "Edinburgh"
        preferences.theme = Dark
    }
```

Standard traits can be derived:

```evert
data Colour =
    Red
  | Green
  | Blue
  deriving Eq, Ord, Hash, Show, Json
```

Traits use coherent implementations. Evert forbids orphan instances by default,
so importing two innocent-looking packages cannot alter the meaning of existing
code.

## Local mutation without surrendering purity

Evert permits encapsulated mutation inside a checked region:

```evert
pure fn histogram(
    values: Vector<Text>
) -> Map<Text, Int> =
    mutate {
        let counts = MutableMap<Text, Int>()

        for value in values {
            counts[value] = counts.getOr(value, 0) + 1
        }

        freeze(counts)
    }
```

The mutable values cannot escape the `mutate` block. The compiler implements
this using a region type equivalent to Haskell’s `ST`, but the programmer need
not conduct a rank-2 polymorphism séance.

The enclosing function remains referentially transparent because callers cannot
observe the mutation itself.

## Small mercies built into the language

Evert would also make several deliberately unromantic choices:

- `Text` is real Unicode text. It is not a linked list of characters.
- Indexing returns `Option<T>` unless the programmer writes an explicit checked
  or panicking form.
- Exceptions appear as `Throw<E>` in the effect row.
- Refutable patterns require `match`; `do` notation never hides a mysterious
  `fail`.
- Public functions require type signatures, while local code receives strong
  inference.
- Type errors describe source-level constructs, not generated dictionaries or
  monadic scaffolding.
- Layout syntax and braces both work.
- Loops exist and compile as loops.
- Persistent collections coexist with efficient mutable builders.
- One compiler command builds, tests, formats and runs the project.
- Language editions replace extension confetti.

The result feels roughly like this:

```evert
data AppError =
    InvalidInput(InputError)
  | UserAlreadyExists(Text)
  | StorageFailure(DatabaseError)

fn register() -> User
    ! { Console, Database, Throw<AppError> } {

    let nameText = Console.ask("Name: ")
    let ageText  = Console.ask("Age: ")

    let user =
        parseUser(nameText, ageText)
            .mapErr(InvalidInput)
            .orThrow()

    let existing =
        Database.findUserByName(user.name)
            .mapErr(StorageFailure)
            .orThrow()

    match existing {
        Some(_) => throw UserAlreadyExists(user.name)
        None    => Database.insert(user)
    }

    Console.say("Registered {user.name}.")
    user
}
```

And the philosophical inversion is complete:

| Haskell                                      | Evert                                                               |
| -------------------------------------------- | ------------------------------------------------------------------- |
| Lazy unless forced                           | Strict unless marked `lazy`                                         |
| Pure by default, `IO` at the boundary        | Effects inferred and tracked; `pure` locks them out                 |
| Monadic syntax for effectful sequencing      | Direct-style effects, monads for intentional abstractions           |
| Mutation requires monadic ceremony           | Local mutation lives inside checked regions                         |
| Effects combine through transformer stacks   | Effects combine through rows and handlers                           |
| Partiality often hides in ordinary functions | Failure appears as `Option`, `Result`, `Throw`, or explicit `panic` |

So Evert still gives you monads, laziness, referential transparency, pure
functions and algebraic data types. It merely declines to deploy all five
simultaneously whenever you attempt to read a configuration file. 🜁

You: Do you think it could be implemented in Rust?

ChatGPT: Yes. I would choose Rust for the first implementation, with one
important rule:

> Use Rust to implement Evert’s semantics, not to encode Evert’s semantics in
> Rust’s type system.

Trying to represent every Evert type as a nest of Rust lifetimes and generics
would produce precisely the cranial-desk interface we are trying to abolish.

A sensible pipeline would be:

```text
source
  → AST
  → resolved HIR
  → typed core language
  → effect/laziness lowering
  → control-flow IR
  → bytecode or Cranelift IR
  → executable
```

Rust suits the compiler front end well. Enums naturally represent syntax and
intermediate representations; arenas, interned values and stable numeric IDs
avoid borrow-checker bramble. Rust’s own compiler relies heavily on arenas and
interning, and separates syntax-oriented HIR from a simpler, fully typed MIR.
([Rust Compiler Development Guide](https://rustc-dev-guide.rust-lang.org/memory.html?utm_source=chatgpt.com))

The internal type representation might look roughly like this:

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct TypeId(u32);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct RowId(u32);

enum Type {
    Variable(TypeVariable),
    Constructor(Symbol),

    Application {
        constructor: TypeId,
        arguments: Vec<TypeId>,
    },

    Function {
        parameter: TypeId,
        result: TypeId,
        effects: RowId,
    },
}

enum EffectRow {
    Empty,

    Extend {
        effect: EffectId,
        tail: RowVariable,
    },

    Variable(RowVariable),
}
```

The type checker would operate on IDs held in arenas, with mutable union-find
tables for unification. It would infer ordinary types and effect rows together,
then elaborate traits into explicit dictionaries.

The truly difficult part is not Rust. It is specifying a coherent combination
of:

- Hindley-Milner-style inference
- higher-kinded constructor parameters such as `M<_>`
- type-class coherence
- open effect rows
- resumable handlers
- local mutation
- polymorphic generalization

I would deliberately omit subtyping and type-level computation from version
one. Evert already has quite enough knives in its cutlery drawer.

Effects would lower selectively into continuation-passing form. Source code
remains direct:

```evert
fn greet() ! Console {
    let name = Console.ask("Name: ")
    Console.say("Hello, {name}.")
}
```

The typed core would make operations explicit:

```text
perform Console.ask("Name: ", continuation)
```

Only code that can perform a resumable effect needs continuation machinery. The
compiler can lower other cases more cheaply:

```text
pure function              → ordinary direct call
Throw<E> only              → Result-like control flow
non-resumable I/O          → direct runtime operation
resumable algebraic effect → continuation-passing form
```

That distinction matters. Compiling the whole program into CPS would work, but
it would tax every function to pay for machinery most never use.

For an initial implementation, I would use a bytecode interpreter. A VM makes
handlers, closures, continuations and garbage-collector roots visible and
tractable. Once the semantics settle, Cranelift would make a good native
backend: it accepts a target-independent low-level IR and emits machine
instructions, and it already supports both JIT and ahead-of-time compiler use
cases.
([GitHub](https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/README.md?utm_source=chatgpt.com))
LLVM could follow when heavyweight optimization becomes worthwhile; Rust’s
compiler itself supports multiple code-generation backends, including LLVM and
Cranelift.
([Rust Compiler Development Guide](https://rustc-dev-guide.rust-lang.org/backend/codegen.html?utm_source=chatgpt.com))

Laziness needs a small runtime state machine:

```rust
enum ThunkState {
    Suspended(Closure),
    Evaluating,
    Evaluated(Value),
}

struct Thunk {
    state: GcCell<ThunkState>,
}
```

Forcing a thunk would:

1. Return the cached value when already evaluated.
2. Mark a suspended thunk as `Evaluating`.
3. Invoke its closure.
4. Replace the closure with the resulting value.
5. Detect recursive forcing through the `Evaluating` state.

Rust’s `OnceCell` and `OnceLock` embody the useful write-once part of this
mechanism, but Evert would need a custom abstraction for black-hole detection,
captured closures and its chosen concurrency semantics.
([Rust Documentation](https://doc.rust-lang.org/beta/std/sync/struct.OnceLock.html?utm_source=chatgpt.com))

Rust ownership does not eliminate the need for garbage collection. Evert
programs can construct closures, lazy recursive values and potentially cyclic
graphs:

```evert
let rec ones = Next(1, lazy ones)
```

Reference counting alone would leak such cycles. I would begin with a
non-moving tracing collector and a shadow-stack or explicit handle scheme. A
non-moving collector contains the necessary `unsafe` code in the runtime and
avoids invalidating pointers held by generated code. Later versions could add
generational collection and precise stack maps.

Strict-by-default evaluation greatly reduces the collector’s burden because
ordinary arithmetic, records and local variables do not automatically become
heap-allocated thunks.

Local mutation is comparatively pleasant. The compiler can represent:

```evert
mutate {
    let buffer = MutableVector<Int>()
    ...
    freeze(buffer)
}
```

as a lexical region with an unforgeable region parameter. The type checker
prevents mutable values from escaping; the implementation can then use ordinary
Rust `Vec`, `HashMap` and mutable references internally. This is one place
where Rust’s ownership model becomes a helpful engine rather than an exposed
user interface.

For monads and traits, I would elaborate:

```evert
do Option {
    x <- first
    y <- second(x)
    yield y
}
```

into calls on an inferred `Monad<Option>` dictionary, then monomorphize common
instances. Higher-kinded parameters would exist in Evert’s compiler, not as
heroic attempts to persuade Rust that `M<_>` is secretly a native Rust type
constructor.

I would organize the implementation approximately like this:

```text
evert_syntax       lexer, parser, source spans
evert_hir          name resolution and desugaring
evert_types        kinds, inference, rows, traits
evert_core         explicitly typed core calculus
evert_lower        closures, thunks, dictionaries, effects
evert_vm           bytecode interpreter
evert_runtime      values, GC, strings, tasks and I/O
evert_codegen      Cranelift backend
evert_driver       CLI, packages, diagnostics
```

A query-oriented compiler architecture would also fit nicely once IDE
responsiveness matters. Rust’s compiler uses demand-driven queries, and Salsa
provides incremental recomputation based on essentially that model.
([Rust Compiler Development Guide](https://rustc-dev-guide.rust-lang.org/queries/incremental-compilation-in-detail.html?utm_source=chatgpt.com))

So yes: Rust can implement Evert cleanly. The compiler would benefit from
Rust’s enums, performance and controlled mutability; the runtime would need a
carefully fenced GC and continuation system. The chief danger is not technical
impossibility. It is attempting row-polymorphic effects, higher kinds,
concurrent laziness, native code generation and self-hosting in the inaugural
commit, thereby constructing a very sophisticated crater.

You: Logos + Chumsky + Salsa + LLVM?

ChatGPT: Yes. That is a coherent stack, with one important insertion:

```text
Logos → layout pass → Chumsky → Salsa queries → custom Core IR → LLVM
```

The layout pass matters because Evert supports Haskell-style indentation. Logos
must retain newlines and indentation rather than discarding all whitespace,
then the pass can inject virtual braces and semicolons before parsing.

I would use:

- Logos for fast, spanned raw tokens.
- Chumsky for grammar, Pratt expressions and error recovery. Logos’s own
  handbook demonstrates the Logos-plus-Chumsky combination directly.
  ([Logos Handbook](https://logos.maciej.codes/examples/calculator.html?utm_source=chatgpt.com))
- Salsa for source files, HIR, name resolution, inferred signatures, effect
  checking and lowered Core. Its tracked and interned values fit compiler IDs
  and symbols particularly well.
  ([Salsa RS](https://salsa-rs.github.io/salsa/about_salsa.html?utm_source=chatgpt.com))
- LLVM strictly as a backend, never as Evert’s semantic representation.

The concrete pipeline should look like this:

```text
source text
  ↓
raw spanned tokens                  Logos
  ↓
layout expansion
  ↓
AST or lossless CST                 Chumsky
  ↓
HIR and stable DefIds
  ↓
kind, type, trait and effect inference
  ↓
explicitly typed Core
  ↓
closure, thunk and handler lowering
  ↓
monomorphic SSA-like LIR
  ↓
LLVM IR
```

Two architectural rules would prevent future table-thumping.

First, do not let borrowed lexer data escape into Salsa. Keep source text as an
input, but represent durable compiler data using byte spans, `FileId`, interned
`Symbol`, `DefId` and owned arena nodes. Logos supports borrowed slices and
precise spans, but those lifetimes become nettlesome once results enter a
persistent incremental database.
([Logos Handbook](https://logos.maciej.codes/examples/json_borrowed.html?utm_source=chatgpt.com))

Second, never store LLVM contexts, modules or builders in Salsa. Salsa queries
should return immutable Evert IR or, at the very edge, object-code bytes.
LLVM’s mutable, lifetime-bound object model should remain quarantined inside
`evert_codegen_llvm`.

A sensible query graph would be:

```text
source(FileId)
tokens(FileId)
parsed_file(FileId)
item_tree(FileId)
module_scope(ModuleId)
resolved_body(DefId)
inferred_signature(DefId)
typed_body(DefId)
core_body(DefId)
mono_instance(InstanceId)
codegen_unit(CodegenUnitId)
```

Type inference deserves special treatment. Each `typed_body` query should
create a private mutable `InferenceContext` containing union-find structures,
metavariables and row constraints. It then solves and “zonks” everything into
an immutable result. Do not put inference metavariables themselves into Salsa.
Recursive definition groups should be identified as strongly connected
components and inferred together.

Salsa also does not magically make Chumsky incrementally parse individual
keystrokes. Editing a file will normally invalidate that file’s complete token
and parse queries. That is perfectly reasonable initially. Later, stable item
IDs let name resolution and type checking remain fine-grained even when parsing
reruns.

LLVM is the one component I would delay as the first executable backend. Begin
with a Core interpreter as the semantic oracle, then make LLVM reproduce the
same test suite. Otherwise, a bug could live in elaboration, effect lowering,
representation selection, LLVM emission or the runtime, and all five suspects
will wear identical trench coats.

For LLVM code generation, keep this interface narrow:

```rust
pub trait Backend {
    type Artifact;

    fn compile(
        &self,
        module: &MonoModule,
        target: &TargetSpec,
    ) -> Result<Self::Artifact, CodegenError>;
}
```

Initially, emitting textual LLVM IR and invoking LLVM tools is surprisingly
attractive. It provides inspectable golden tests and avoids binding churn. An
embedded backend can later use Inkwell for ordinary IR construction, with
`llvm-sys` or a small C++ bridge for facilities Inkwell does not expose
adequately.

Evert’s runtime remains your responsibility. LLVM supports stack maps,
safepoints and GC statepoints, but deliberately does not supply a garbage
collector.
([LLVM](https://llvm.org/docs/GarbageCollection.html?utm_source=chatgpt.com))
I would start with:

```text
non-moving tracing GC
explicit shadow-stack roots
boxed closures and thunks
C-compatible runtime ABI
stop-the-world collection
```

That avoids statepoint complexity while the object model is still liquid. A
moving or generational collector can use statepoints later.

Likewise, do not expect LLVM coroutine intrinsics to implement algebraic
effects for you. Lower handlers and resumable operations into Evert’s own
continuation representation before LLVM sees them. One-shot continuations can
become heap frames plus resume functions; multi-shot continuations require
cloning persistent continuation frames. LLVM should receive ordinary control
flow, calls and data structures, not a half-digested theory paper.

I would divide the repository roughly as follows:

```text
evert_span
evert_syntax          # Logos, Chumsky, layout expansion
evert_db              # Salsa database and query declarations
evert_hir
evert_typeck
evert_core
evert_lower
evert_interpreter
evert_runtime
evert_codegen_api
evert_codegen_llvm
evert_driver
```

So yes: Logos + Chumsky + Salsa + LLVM, with a layout expander, an interpreter
and a custom intermediate language between Salsa and LLVM. That gives Evert a
sturdy chassis without welding its type theory directly to the optimiser.

You: Please draft ECLP's (Evert Core Language Proposals) for each major
capability and of the language. Like PEPs but before we started extending it 😊

Start with core tenets, mission statement, data model, types, function model,
module architecture, laziness, monadicity, etc. Then go wild. Don't add quantum
computing primitives yet, but feel free to design a 1st class
concurrency/ownership system that addresses the things that annoy you about
Rust, Go, Swift and Mojolang (and steals liberally where it makes sense).

Use the attached peglet meta-syntax for representing language structures in a
unified fashion, be aggressive about consistency, and encourage creativity.
🏗️🖥️🐿️

ChatGPT: I’ll frame this as a founding ECLP bundle: numbered, opinionated
proposals with rationale, semantics, syntax, and peglet sketches as the shared
notation.I’ll make each ECLP tie surface syntax, static semantics, runtime
lowering, and peglet structure together, treating peglet fragments as normative
sketches rather than the whole compiler.

Absolutely. Here is ECLP-0000 through ECLP-0024, the first seed-crystal of
Evert’s constitution: not “extensions” yet, but the language’s spine, organs,
temper, and small brass squirrel engine.

I’ve treated the attached `peglet` document as the normative metalanguage for
syntax sketches. That is a good fit because `peglet` explicitly aims to “write
the grammar once”, make tokenisation explicit, preserve structure for AST or
CST generation, and expose PEG-specific behaviour rather than pretending
ordered choice behaves like ordinary alternation.  Its separation of tokens and
trivia is exactly what Evert wants for compiler diagnostics, formatting and
IDE-grade CSTs.  I’m also leaning on its rule structure, declarative
constructors, Pratt blocks, cuts and recovery clauses because they give us a
consistent notation without sneaking Rust actions into the grammar.

I’m reading “Mojolang” as Mojo, since its current manual organizes language
material around functions, modules, value ownership, lifetimes, traits,
generics, pointers and GPU programming, which makes it a useful foil for the
“systems language without ritualized splinters” part of Evert.
([docs.modular.com](https://docs.modular.com/mojo/manual/))

## ECLP-0000: The Evert Mission

Status: Foundational Draft

Evert exists to make the following sentence true:

> A programmer should be able to write direct, readable code and still receive
> the benefits of purity, laziness, algebraic effects, monads, algebraic data
> types, local mutation, deterministic resource handling, and race-safe
> concurrency, without having to conscript the whole programme into whichever
> abstraction they touched last.

Evert is inside-out Haskell: the elegant machinery remains available, but it
lives behind explicit doors.

The core tenets are:

1. Power is local. A function that uses laziness, effects, mutation,
   concurrency, unsafe memory, or monadic sequencing should say so near the
   code that needs it.

2. Purity is enforceable, not performative. `pure fn` means empty effect row.
   It is a compiler promise, not a comment in a lab coat.

3. Strictness is default. Laziness is explicit. Laziness remains a tool for
   streams, memoization and recursive structures, not an invisible global
   climate system.

4. Effects are typed. Effects are handled. Effects do not infect everything.
   Ambient `IO` does not become the whale that swallowed the language.

5. Monads are abstractions, not penance. Evert supports monads fully, including
   higher-kinded constructors and `do`, but direct-style effects remain direct.

6. Values are immutable unless scoped mutation says otherwise. Mutation lives
   in checked regions, actor state, atomics, or unsafe blocks.

7. Concurrency is structured. No orphan goroutines. No invisible child tasks
   chewing wires in the walls. No actor reentrancy trapdoors by default.

8. Ownership is semantic, not decorative. Linear resources, borrowing and
   transfer exist, but ordinary application code should not drown in lifetime
   runes.

9. Unsafe code is explicit, fenced and auditable. Evert should let you do
   frightening things, but only inside a room with hazard stripes and excellent
   lighting.

10. Diagnostics are part of the language design. A construct that cannot
    explain itself to a tired human at 01:43 does not deserve syntax.

## ECLP-0001: ECLP Format

Status: Accepted for Drafting

Every ECLP uses this shape:

```text
ECLP: number
Title: short noun phrase
Status: Draft | Accepted | Deferred | Rejected | Superseded
Layer: Lexical | Syntax | Static Semantics | Runtime | Tooling | Library
Requires: other ECLPs
Summary
Specification
Peglet Form
Examples
Rationale
Open Questions
```

ECLPs are not feature requests. They are compact design decisions with enough
grammar, semantics and examples to build against.

## ECLP-0002: Surface Grammar Contract

Status: Foundational Draft

Evert source syntax uses a CST-first grammar. The compiler may lower to an AST
after preserving tokens, trivia, spans and recovery nodes.

Evert supports both braces and layout, but the grammar sees explicit `Indent`,
`Dedent` and `Newline` tokens after a layout pass. This prevents Haskell-grade
whitespace sorcery from oozing into every parser rule.

```peglet
@grammar evert.surface
@start source_file
@token_type TokenKind
@span Span
@trivia [Whitespace, LineComment, BlockComment] retain
@backend chumsky

lexer {
    token Module     = "module";
    token Use        = "use";
    token Export     = "export";
    token Data       = "data";
    token Record     = "record";
    token Type       = "type";
    token Trait      = "trait";
    token Impl       = "impl";
    token Effect     = "effect";
    token Handler    = "handler";
    token Fn         = "fn";
    token Pure       = "pure";
    token Let        = "let";
    token Var        = "var";
    token Lazy       = "lazy";
    token Rec        = "rec";
    token Mutate     = "mutate";
    token Match      = "match";
    token If         = "if";
    token Else       = "else";
    token Do         = "do";
    token Yield      = "yield";
    token Return     = "return";
    token Throw      = "throw";
    token Try        = "try";
    token Handle     = "handle";
    token With       = "with";
    token Own        = "own";
    token Borrow     = "borrow";
    token Inout      = "inout";
    token Send       = "send";
    token Using      = "using";
    token Nursery    = "nursery";
    token Spawn      = "spawn";
    token Await      = "await";
    token Cancel     = "cancel";
    token Actor      = "actor";
    token Protocol   = "protocol";
    token Receive    = "receive";
    token Select     = "select";
    token Unsafe     = "unsafe";
    token Extern     = "extern";

    token Ident      = /[A-Za-z_][A-Za-z0-9_]*/;
    token RawIdent   = /r#[A-Za-z_][A-Za-z0-9_]*/;
    token Int        = /[0-9][0-9_]*/;
    token Float      = /[0-9][0-9_]*\.[0-9][0-9_]*/;
    token String     = /"([^"\\]|\\.)*"/;
    token Char       = /'([^'\\]|\\.)'/;

    token Arrow      = "->";
    token FatArrow   = "=>";
    token Bang       = "!";
    token Question   = "?";
    token ColonColon = "::";
    token DotDot     = "..";
    token Pipe       = "|";
    token Amp        = "&";
    token Eq         = "=";
    token Colon      = ":";
    token Semi       = ";";
    token Comma      = ",";
    token Dot        = ".";
    token LParen     = "(";
    token RParen     = ")";
    token LBrace     = "{";
    token RBrace     = "}";
    token LBracket   = "[";
    token RBracket   = "]";
    token Lt         = "<";
    token Gt         = ">";

    trivia Whitespace   = /[ \t\r\n]+/;
    trivia LineComment  = /\/\/[^\n]*/;
    trivia BlockComment = /\/\*([^*]|\*+[^*/])*\*+\//;
}

source_file =
    module:module_decl? uses:use_decl* items:item* EOF
    => SourceFile { module, uses, items }
;
```

Evert grammar uses cuts after distinctive prefixes. That keeps diagnostics
pinned to the construct the programmer actually started writing, rather than
letting the parser wander off with a lantern and a false theory.

## ECLP-0003: Mission-Level Syntax

Status: Draft

Top-level syntax starts boring and stays boring. Evert favours a small number
of declarations with uniform bodies.

```peglet
item =
      module_decl
    / use_decl
    / export_decl
    / data_decl
    / record_decl
    / type_alias
    / trait_decl
    / impl_decl
    / effect_decl
    / handler_decl
    / fn_decl
    / actor_decl
    / protocol_decl
    / extern_decl
;

module_decl =
    Module ~ path:qualified_name Semi
    => ModuleDecl(path)
    recover until [Semi, EOF]
;

use_decl =
    Use ~ tree:use_tree Semi
    => UseDecl(tree)
    recover until [Semi, EOF]
;

export_decl =
    Export ~ exports:export_set Semi
    => ExportDecl(exports)
    recover until [Semi, EOF]
;
```

Evert does not use significant import side effects. Importing a module never
runs arbitrary code. Modules may expose constants, functions, types, traits,
effects, handlers, actors and protocol definitions, but not surprise goblins.

## ECLP-0004: The Data Model

Status: Foundational Draft

Evert has five semantic value classes:

```text
Plain value       immutable, shareable, no observable identity
Lazy value        pure suspended computation, memoized after forcing
Resource value    linear or affine value with deterministic finalization
Cell value        region-bound mutable storage
Capability value  authority to perform an effect, access a service, or communicate
```

Representation is not semantics. An immutable `Text` may point to shared heap
storage, a small array, an interned rope, or a dragon-shaped arena allocation.
Evert source code cannot tell unless the type exposes identity deliberately.

Core data declarations:

```evert
data Option<T> =
    None
  | Some(T)

data Result<T, E> =
    Ok(T)
  | Err(E)

record User {
    id: UserId,
    name: Text,
    email: Option<Text>
}
```

Peglet form:

```peglet
@node
data_decl =
    Data ~ name:type_name params:type_params? Eq ctors:ctor_decl++Pipe
    => DataDecl { name, params, ctors }
    recover until [Semi, RBrace, EOF]
;

@node
ctor_decl =
    name:type_name fields:ctor_fields?
    => CtorDecl { name, fields }
;

ctor_fields =
      LParen fields:type_expr**Comma RParen => PositionalFields(fields)
    / LBrace fields:field_decl**Comma RBrace => NamedFields(fields)
;

@node
record_decl =
    Record ~ name:type_name params:type_params? body:record_body
    => RecordDecl { name, params, body }
    recover nested LBrace RBrace until [EOF]
;

record_body =
    LBrace fields:record_field**Comma RBrace
    => fields
;

record_field =
    attrs:attr* name:Ident Colon ty:type_expr default:(Eq expr)?
    => RecordField { attrs, name, ty, default }
;
```

Semantic rules:

```text
Plain values have no observable identity.
Record update creates a new value unless the receiver is a mutable cell.
Constructors are total functions.
Destructors exist only for Resource values.
Equality is never implicit for functions, effects, actors, tasks or resources.
```

Nested updates exist without requiring a lens monastery:

```evert
let updated =
    user with {
        email = Some("payton@example.net")
        profile.address.city = "Edinburgh"
    }
```

## ECLP-0005: Type System, Kinds and Rows

Status: Foundational Draft

Evert uses nominal algebraic types, structural effect rows, row-polymorphic
function types, traits, higher-kinded type parameters and inference with
explicit public signatures.

Kinds:

```text
Type              ordinary inhabited types
Effect            effect constructors
EffectRow         rows of effects
Region            compiler-managed region identity
Capability        authority token kind
Protocol          actor or channel protocol kind
```

Source programmers normally see `Type`, `Effect` and `EffectRow`. `Region`
appears in diagnostics and unsafe code, not in daily application work.

Type examples:

```evert
Text
Vector<Int>
Map<Text, User>
Option<Text>
Result<User, DecodeError>
A -> B
A -> B ! Console
A -> B ! { Console, Clock, Throw<DecodeError> }
forall<T>. Vector<T> -> Int
```

Peglet form:

```peglet
type_expr = pratt {
    atom: type_atom;

    postfix [Question] bp 80 => OptionalType(lhs);
    infix right [Arrow] bp 20 => FunctionType(lhs, rhs);
};

type_atom =
      name:qualified_name args:type_args? => TypeName { name, args }
    / LParen items:type_expr**Comma RParen => TupleType(items)
    / LBrace fields:type_field**Comma RBrace => RecordType(fields)
    / Bang row:effect_row => EffectRowType(row)
;

effect_row =
      LBrace effects:effect_item**Comma RBrace => ClosedEffectRow(effects)
    / name:Ident => EffectRowVar(name)
;

effect_item =
    name:qualified_name args:type_args?
    => EffectItem { name, args }
;

type_args =
    Lt args:type_expr++Comma Gt
    => args
;
```

Function types attach effects to arrows:

```evert
Text -> Int
Text -> Int ! Throw<ParseError>
Url -> Page ! { Http, Throw<NetworkError>, Clock }
```

`pure fn` means the inferred effect row must be empty:

```evert
pure fn square(x: Int) -> Int =
    x * x
```

This fails:

```evert
pure fn nowish() -> Instant =
    Clock.now()
```

Diagnostic:

```text
Clock.now performs Clock.
pure fn nowish permits no effects.
```

No passive-aggressive type-variable thunderstorm. Just the problem.

## ECLP-0006: Function Model

Status: Foundational Draft

Evert has direct-style functions with explicit public signatures and inferred
private signatures.

Function parameter modes:

```text
x: T          semantic value, immutable
own x: T      consumes a resource or linear value
borrow x: T   read-only non-escaping borrow
inout x: T    exclusive non-escaping mutable borrow
send x: T     transfer across concurrency boundary
```

Non-resource values use semantic value passing. The compiler may copy, share,
borrow or scalarize. Resource values require explicit ownership mode.

Peglet form:

```peglet
@node
fn_decl =
    purity:purity? Fn ~ name:Ident params:type_params? args:param_list
    ret:return_type? eff:effect_sig? body:fn_body
    => FnDecl { purity, name, params, args, ret, eff, body }
    recover until [RBrace, Semi, EOF]
;

purity =
      Pure => Pure
;

param_list =
    LParen params:param**Comma RParen
    => params
;

param =
    mode:param_mode? name:Ident Colon ty:type_expr
    => Param { mode, name, ty }
;

param_mode =
      Own    => Own
    / Borrow => Borrow
    / Inout  => Inout
    / Send   => Send
;

return_type =
    Arrow ty:type_expr
    => ty
;

effect_sig =
    Bang row:effect_row
    => row
;

fn_body =
      Eq value:expr Semi => ExprBody(value)
    / block => BlockBody(block)
;
```

Examples:

```evert
pure fn add(x: Int, y: Int) -> Int =
    x + y

fn load(path: Path) -> Text ! { FileSystem, Throw<IoError> } {
    FileSystem.readText(path)
}

fn close(own socket: Socket) -> Unit ! Network {
    socket.close()
}

fn fill(inout buffer: MutableVector<Int>, value: Int) {
    for i in buffer.indices() {
        buffer[i] = value
    }
}
```

Open question: Should `fn` infer effects silently for private functions, or
should the compiler display inferred signatures during hover and require
explicit effects whenever a function crosses a module boundary? Current answer:
yes.

## ECLP-0007: Blocks, Statements and Expressions

Status: Draft

Evert is expression-oriented, but it does not pretend loops are shameful.

```peglet
@node
block =
    LBrace stmts:stmt* tail:expr? RBrace
    => Block { stmts, tail }
    recover nested LBrace RBrace until [EOF]
;

stmt =
      let_stmt
    / var_stmt
    / using_stmt
    / return_stmt
    / throw_stmt
    / expr_stmt
;

@node
let_stmt =
    Let ~ pattern:pattern ann:type_ann? Eq value:expr Semi
    => LetStmt { pattern, ann, value }
    recover until [Semi, RBrace, EOF]
;

@node
var_stmt =
    Var ~ name:Ident ann:type_ann? Eq value:expr Semi
    => VarStmt { name, ann, value }
    recover until [Semi, RBrace, EOF]
;

@node
return_stmt =
    Return ~ value:expr? Semi
    => ReturnStmt(value)
    recover until [Semi, RBrace, EOF]
;

@node
expr_stmt =
    value:expr Semi
    => ExprStmt(value)
    recover until [Semi, RBrace, EOF]
;
```

`let` binds immutable values. `var` exists only in mutation-allowed contexts:
local imperative code, `mutate`, actor state initialization, unsafe blocks and
generated lowering.

A block’s final expression is its value:

```evert
let message = {
    let name = "Payton";
    "Hello, {name}"
}
```

## ECLP-0008: Algebraic Data Types and Pattern Matching

Status: Foundational Draft

Pattern matching must be exhaustive unless the scrutinee type is open.

```peglet
@node
match_expr =
    Match ~ scrutinee:expr LBrace arms:match_arm+ RBrace
    => MatchExpr { scrutinee, arms }
    recover nested LBrace RBrace until [EOF]
;

match_arm =
    pat:pattern guard:guard? FatArrow body:expr Comma?
    => MatchArm { pat, guard, body }
;

guard =
    If cond:expr
    => cond
;

pattern =
      wildcard_pat
    / literal_pat
    / ctor_pat
    / record_pat
    / tuple_pat
    / binding_pat
;

wildcard_pat =
    Underscore => Wildcard
;

binding_pat =
    name:Ident => Binding(name)
;

ctor_pat =
    name:qualified_name args:pattern_args?
    => ConstructorPattern { name, args }
;
```

Example:

```evert
pure fn describe(result: Result<User, Error>) -> Text =
    match result {
        Ok(User { name, email: Some(email), .. }) =>
            "{name} <{email}>",

        Ok(User { name, email: None, .. }) =>
            "{name}",

        Err(e) =>
            "error: {e}"
    }
```

Refutable patterns require `match`, `if let`, or `case`. `let Some(x) = maybe;`
is illegal unless the type system proves totality.

## ECLP-0009: Laziness

Status: Foundational Draft

Evert is strict by default. Laziness appears only through `lazy`.

```evert
let lazy cached = expensivePureComputation()
```

A `lazy` expression must be pure. This is non-negotiable. The evaluation time
of a lazy expression must not affect observable effects.

```evert
let lazy line = Console.readLine()
```

Diagnostic:

```text
Cannot make an effectful expression lazy.

Console.readLine performs Console.
Use `task { ... }` for deferred effects.
```

Peglet form:

```peglet
@node
lazy_let_stmt =
    Let Lazy ~ pattern:pattern ann:type_ann? Eq value:expr Semi
    => LazyLetStmt { pattern, ann, value }
    recover until [Semi, RBrace, EOF]
;

type_atom =
      Lazy ty:type_atom => LazyType(ty)
    / name:qualified_name args:type_args? => TypeName { name, args }
    / LParen items:type_expr**Comma RParen => TupleType(items)
;
```

Lazy fields:

```evert
data Stream<T> =
    End
  | Next(head: T, tail: lazy Stream<T>)

pure fn naturals(n: Int) -> Stream<Int> =
    Next(n, lazy naturals(n + 1))
```

Runtime semantics:

```text
lazy e creates a thunk.
Forcing a thunk evaluates e at most once.
Successful result is memoized.
Recursive forcing of the same thunk reports a black-hole error.
Concurrent forcing synchronizes, then shares the result.
A thunk may not contain observable effects.
```

`lazy` is not `async`, not `defer`, not `IO wearing slippers`.

## ECLP-0010: Monadicity

Status: Draft

Evert supports monads as ordinary abstractions:

```evert
trait Monad<M<_>> {
    pure<T>(value: T) -> M<T>

    flatMap<A, B>(
        value: M<A>,
        next: A -> M<B>
    ) -> M<B>
}
```

`do M { ... }` uses the `Monad<M>` instance. It does not mean “perform effects”.

Peglet form:

```peglet
@node
do_expr =
    Do ~ target:type_expr LBrace steps:do_step* RBrace
    => DoExpr { target, steps }
    recover nested LBrace RBrace until [EOF]
;

do_step =
      do_bind
    / do_let
    / do_ensure
    / do_yield
;

do_bind =
    pattern:pattern LeftArrow value:expr Semi
    => DoBind { pattern, value }
;

do_let =
    Let pattern:pattern Eq value:expr Semi
    => DoLet { pattern, value }
;

do_ensure =
    Ensure cond:expr Else err:expr Semi
    => DoEnsure { cond, err }
;

do_yield =
    Yield value:expr Semi
    => DoYield(value)
;
```

Example:

```evert
pure fn billingEmail(
    users: Map<UserId, User>,
    id: UserId
) -> Option<Text> =
    do Option {
        user <- users.get(id);
        account <- user.billingAccount;
        email <- account.email;
        yield email;
    }
```

For `Result`:

```evert
pure fn parsePort(text: Text) -> Result<Port, ParseError> =
    do Result {
        n <- Int.parse(text).mapErr(BadInteger);
        ensure n >= 0 else TooSmall(n);
        ensure n <= 65535 else TooLarge(n);
        yield Port(n);
    }
```

Design law:

```text
Effects use effect rows and handlers.
Data-level sequencing uses monads.
The two may lower to similar core forms.
The source language does not confuse them.
```

## ECLP-0011: Algebraic Effects and Handlers

Status: Foundational Draft

Effects are named sets of operations.

```evert
effect Console {
    ask(prompt: Text) -> Text
    say(message: Text) -> Unit
}

effect Clock {
    now() -> Instant
}
```

Peglet form:

```peglet
@node
effect_decl =
    Effect ~ name:type_name params:type_params? LBrace ops:effect_op* RBrace
    => EffectDecl { name, params, ops }
    recover nested LBrace RBrace until [EOF]
;

effect_op =
    name:Ident args:param_list ret:return_type? Semi
    => EffectOp { name, args, ret }
;
```

Using effects:

```evert
fn greet() -> Unit ! { Console, Clock } {
    let name = Console.ask("Name: ");
    let now = Clock.now();
    Console.say("[{now}] Hello, {name}");
}
```

Handling effects:

```evert
let output =
    handle greet() with {
        Console.ask(prompt) resume =>
            resume("Payton")

        Console.say(message) resume =>
            transcript.push(message);
            resume(())
    }
```

Handler grammar:

```peglet
@node
handle_expr =
    Handle ~ value:expr With handler:handler_body
    => HandleExpr { value, handler }
    recover nested LBrace RBrace until [EOF]
;

handler_body =
    LBrace clauses:handler_clause* RBrace
    => HandlerBody(clauses)
;

handler_clause =
    op:qualified_name args:handler_args resume:resume_clause? FatArrow body:block
    => HandlerClause { op, args, resume, body }
;

resume_clause =
    Resume name:Ident
    => name
;
```

Effect rules:

```text
A function type carries an effect row.
A handler may eliminate, transform or re-emit effects.
Unhandled effects remain in the enclosing expression’s row.
Non-resumable effects are declared explicitly.
Throw<E> is an effect, not an untyped exception chute.
```

## ECLP-0012: Errors, Partiality and Contracts

Status: Draft

Evert has three ordinary failure channels:

```text
Option<T>            absence
Result<T, E>         value-level recoverable failure
Throw<E>             effect-level early exit
```

`panic` exists, but it is explicit and unsuitable for ordinary control flow.

```evert
fn parseUser(text: Text) -> User ! Throw<ParseError> {
    let json = Json.parse(text).orThrow();
    decodeUser(json).orThrow()
}
```

Postfix `?` is value-level sugar only when the surrounding context supports it:

```evert
pure fn host(url: Url) -> Result<Text, UrlError> {
    let authority = url.authority?;
    Ok(authority.host)
}
```

Peglet expression hook:

```peglet
expr = pratt {
    atom: primary;

    postfix [Question] bp 90 => TryPostfix(lhs);
    prefix [Throw] bp 20 => ThrowExpr(rhs);
    infix left [Dot] bp 95 => FieldAccess(lhs, rhs);
};
```

Contracts:

```evert
pure fn sqrt(x: Float) -> Float
    requires x >= 0.0
    ensures result >= 0.0
{
    intrinsic.sqrt(x)
}
```

Rules:

```text
requires and ensures expressions must be pure.
The name result is bound in ensures.
Contracts may compile to runtime checks, tests, proof obligations, or documentation.
Unchecked indexing is spelled explicitly.
```

Indexing defaults to safety:

```evert
xs.get(i)        // Option<T>
xs[i]!          // explicit panic on out of bounds
xs[i]?          // Result/Throw propagation
```

## ECLP-0013: Local Mutation and Regions

Status: Foundational Draft

Mutation is allowed in lexical regions whose mutable values cannot escape.

```evert
pure fn histogram(words: Vector<Text>) -> Map<Text, Int> =
    mutate {
        var counts = MutableMap<Text, Int>();

        for word in words {
            counts[word] = counts.getOr(word, 0) + 1;
        }

        freeze(counts)
    }
```

The enclosing function remains pure because callers cannot observe mutation.

Peglet form:

```peglet
@node
mutate_expr =
    Mutate ~ block
    => MutateExpr(block)
    recover nested LBrace RBrace until [EOF]
;

@node
assignment_stmt =
    target:assign_target Eq value:expr Semi
    => AssignStmt { target, value }
    recover until [Semi, RBrace, EOF]
;

assign_target =
      name:Ident => AssignName(name)
    / base:expr Dot field:Ident => AssignField { base, field }
    / base:expr LBracket index:expr RBracket => AssignIndex { base, index }
;
```

Static rules:

```text
Mutable cells carry an implicit region.
The region may not escape its block.
freeze consumes a mutable builder and returns an immutable value.
inout parameters may not be captured by escaping closures.
pure functions may contain mutate if the mutation is fully encapsulated.
```

This steals the useful part of Haskell’s `ST`, then hides the ceremonial
antlers.

## ECLP-0014: Traits, Instances and Coherence

Status: Draft

Traits describe ad-hoc polymorphism.

```evert
trait Show<T> {
    show(value: T) -> Text
}

impl Show<User> {
    show(user: User) -> Text =
        "{user.name}#{user.id}"
}
```

Higher-kinded traits:

```evert
trait Functor<F<_>> {
    map<A, B>(fa: F<A>, f: A -> B) -> F<B>
}

trait Monad<M<_>> : Functor<M> {
    pure<T>(value: T) -> M<T>
    flatMap<A, B>(ma: M<A>, f: A -> M<B>) -> M<B>
}
```

Peglet form:

```peglet
@node
trait_decl =
    Trait ~ name:type_name params:type_params? supers:super_traits? body:trait_body
    => TraitDecl { name, params, supers, body }
    recover nested LBrace RBrace until [EOF]
;

trait_body =
    LBrace members:trait_member* RBrace
    => members
;

trait_member =
      fn_sig
    / assoc_type
    / law_decl
;

@node
impl_decl =
    Impl ~ params:type_params? target:trait_impl_target body:impl_body
    => ImplDecl { params, target, body }
    recover nested LBrace RBrace until [EOF]
;
```

Coherence rules:

```text
No orphan impls by default.
An impl is legal if the current module owns the trait or the target type.
Overlapping impls are rejected unless marked specialization and proven coherent.
Trait laws may be declared and tested.
```

Derivation:

```evert
data Colour =
    Red | Green | Blue
    deriving Eq, Ord, Hash, Show, Json
```

Evert treats trait dictionaries as an elaboration detail. Users see clean
errors:

```text
No Show<User> implementation is in scope.
```

Not:

```text
could not solve ?d_show_user in canonicalized obligation universe 3
```

## ECLP-0015: Module and Package Architecture

Status: Draft

A module is a namespace and visibility boundary. A package is a versioned set
of modules.

```evert
module app.billing.invoice;

use std.text.{Text, Builder};
use std.time.Clock;
use app.money.Money;

export {
    Invoice,
    renderInvoice,
}
```

Rules:

```text
Imports are explicit.
Imports have no runtime effects.
Module initialization is forbidden.
Public declarations require explicit type and effect signatures.
Private declarations may use inference.
Exported impls obey coherence rules.
```

Peglet form:

```peglet
qualified_name =
    head:Ident rest:(Dot Ident)*
    => QualifiedName { head, rest }
;

use_tree =
      path:qualified_name => UsePath(path)
    / prefix:qualified_name Dot LBrace items:use_tree**Comma RBrace
        => UseGroup { prefix, items }
    / path:qualified_name As alias:Ident
        => UseAlias { path, alias }
;

export_set =
    LBrace items:export_item**Comma RBrace
    => items
;

export_item =
      name:Ident => ExportName(name)
    / name:Ident As alias:Ident => ExportAlias { name, alias }
;
```

No global constructors. No import-time database connections. No “why did
importing the formatter start a web server?” incidents.

## ECLP-0016: Ownership Without Lifetime Graffiti

Status: Foundational Draft

Evert has ownership, but safe Evert avoids explicit lifetime parameters.

Kinds of ownership:

```text
Plain<T>      immutable semantic value
Linear<T>     exactly one owner, must be consumed
Affine<T>     at most one owner, may be discarded
Borrow<T>     read-only non-escaping view
Inout<T>      exclusive non-escaping mutable view
Pinned<T>     address-stable value for FFI or runtime internals
```

Parameter modes, repeated because they matter:

```evert
fn inspect(borrow file: File) -> Metadata ! FileSystem
fn close(own file: File) -> Unit ! FileSystem
fn fill(inout buffer: MutableBuffer, byte: UInt8) -> Unit
fn transfer(send packet: Packet) -> Unit ! Network
```

Resource management:

```evert
using file = File.open(path)?;
let text = file.readText()?;
```

`using` guarantees deterministic finalization at the end of scope, including
cancellation and thrown errors.

Peglet form:

```peglet
@node
using_stmt =
    Using ~ pattern:pattern Eq value:expr Semi
    => UsingStmt { pattern, value }
    recover until [Semi, RBrace, EOF]
;

resource_bound =
      Own ty:type_expr => OwnType(ty)
    / Borrow ty:type_expr => BorrowType(ty)
    / Inout ty:type_expr => InoutType(ty)
    / Send ty:type_expr => SendType(ty)
;
```

Rules:

```text
Plain values can be freely shared.
Linear values cannot be copied.
Affine values can be dropped without use.
Resource values must be transferred, borrowed, or consumed explicitly.
Safe Evert does not expose lifetime parameters.
Diagnostics may name inferred origins in plain English.
Unsafe Evert may use explicit regions and raw pointers.
```

This is where Evert steals from Rust, then removes the part where your morning
disappears into a variance diagram.

## ECLP-0017: First-Class Concurrency

Status: Foundational Draft

Evert concurrency is structured, typed and ownership-aware.

The core construct is a nursery. Child tasks cannot outlive the nursery that
spawned them.

```evert
fn fetchAll(urls: Vector<Url>) -> Vector<Page>
    ! { Async, Http, Throw<NetworkError> } {

    nursery n {
        let tasks =
            urls.map(url =>
                n.spawn {
                    Http.get(url)
                }
            );

        tasks.map(task => await task)
    }
}
```

Peglet form:

```peglet
@node
nursery_expr =
    Nursery ~ name:Ident? block
    => NurseryExpr { name, block }
    recover nested LBrace RBrace until [EOF]
;

@node
spawn_expr =
    Spawn ~ target:spawn_target? block
    => SpawnExpr { target, block }
    recover nested LBrace RBrace until [EOF]
;

spawn_target =
      name:Ident Dot Spawn => NurserySpawn(name)
    / Spawn => AmbientSpawn
;

@node
await_expr =
    Await ~ value:expr
    => AwaitExpr(value)
;
```

Static rules:

```text
spawn is only legal inside a nursery unless explicitly detached in unsafe/system code.
A spawned task may capture Plain values.
A spawned task may capture borrow values only if the borrow cannot outlive the nursery.
A spawned task may capture Linear or Affine values only by move.
A spawned task may not capture inout values unless the task is proven serial.
await propagates task failure and cancellation according to the task type.
Leaving a nursery awaits or cancels all children.
```

Task type:

```evert
Task<T, E>
```

where `E` is the child’s effect or failure row after runtime interpretation.

Race:

```evert
let page =
    race {
        primary: Http.get(primaryUrl)
        mirror:  Http.get(mirrorUrl)
    }
```

Semantics:

```text
race returns the first successful branch.
Losing branches are cancelled.
If all branches fail, the combined failure is returned or thrown.
Finalizers run for all branches.
```

Cancellation is typed:

```evert
fn serve() -> Unit ! { Async, Network, Cancel } {
    nursery clients {
        loop {
            let socket = Network.accept();
            clients.spawn {
                handleClient(socket)
            }
        }
    }
}
```

Cancellation is cooperative but checked at suspension points. `using`
finalizers run during cancellation. This avoids Go’s orphan goroutine swamp,
Rust async’s self-referential puzzle boxes, and Swift’s “is this actor method
secretly reentrant now?” card trick.

## ECLP-0018: Channels, Ports and Select

Status: Draft

Channels are typed resources with explicit endpoints.

```evert
let (tx, rx) = Channel<Text>.bounded(64);

nursery n {
    n.spawn {
        send tx <- "hello";
    };

    let msg = receive rx;
}
```

Endpoints:

```text
Sender<T>     send-only endpoint
Receiver<T>   receive-only endpoint
Channel<T>    paired constructor, not usually stored
```

Peglet form:

```peglet
@node
send_expr =
    Send ~ target:expr LeftArrow value:expr
    => SendExpr { target, value }
;

@node
receive_expr =
    Receive ~ source:expr
    => ReceiveExpr(source)
;

@node
select_expr =
    Select ~ LBrace arms:select_arm+ RBrace
    => SelectExpr(arms)
    recover nested LBrace RBrace until [EOF]
;

select_arm =
    op:select_op FatArrow body:expr Comma?
    => SelectArm { op, body }
;

select_op =
      Send target:expr LeftArrow value:expr => SelectSend { target, value }
    / Receive source:expr => SelectReceive(source)
    / Await task:expr => SelectAwait(task)
;
```

Rules:

```text
Sending requires Send<T>.
Receiving consumes readiness, not ownership of the channel.
Closing a sender is deterministic when its endpoint is dropped.
select is fair by default within one scheduler tick.
Biased select must be written `select biased`.
```

No silent global queues. No unbounded channels unless the programmer writes
`unbounded` and accepts the goblin.

## ECLP-0019: Actors and Protocols

Status: Draft

Actors isolate state behind protocols.

```evert
protocol Counter {
    inc(delta: Int) -> Unit
    get() -> Int
}

actor CounterActor : Counter {
    state count: Int = 0

    fn inc(delta: Int) {
        count = count + delta
    }

    fn get() -> Int {
        count
    }
}
```

Peglet form:

```peglet
@node
protocol_decl =
    Protocol ~ name:type_name params:type_params? body:protocol_body
    => ProtocolDecl { name, params, body }
    recover nested LBrace RBrace until [EOF]
;

protocol_body =
    LBrace members:protocol_member* RBrace
    => members
;

protocol_member =
    fn_sig Semi
    => ProtocolFn(fn_sig)
;

@node
actor_decl =
    Actor ~ name:type_name params:type_params? implements:actor_impl? body:actor_body
    => ActorDecl { name, params, implements, body }
    recover nested LBrace RBrace until [EOF]
;

actor_impl =
    Colon protocols:qualified_name++Comma
    => protocols
;

actor_body =
    LBrace members:actor_member* RBrace
    => members
;

actor_member =
      actor_state
    / fn_decl
;

actor_state =
    State ~ name:Ident Colon ty:type_expr Eq value:expr Semi
    => ActorState { name, ty, value }
;
```

Actor rules:

```text
Actor state is isolated.
Only actor methods can access actor state.
Messages must be Send.
Actor methods are non-reentrant by default.
An actor method may not await while holding mutable access to actor state.
Reentrancy requires explicit `reentrant fn`.
```

This last rule matters. Swift-style actor reentrancy can be powerful, but it
also creates temporal spaghetti. Evert chooses non-reentrant actors by default,
then lets experts opt into reentrancy with syntax large enough to trip over.

Example:

```evert
actor BankAccount {
    state balance: Money = Money.zero()

    fn withdraw(amount: Money) -> Result<Unit, AccountError> {
        if balance < amount {
            Err(InsufficientFunds)
        } else {
            balance = balance - amount;
            Ok(())
        }
    }

    reentrant fn refreshExchangeRate() -> Unit ! { Http, Clock } {
        let rate = await Http.get(exchangeRateUrl);
        // State access resumes only after await boundary.
        updateRate(rate)
    }
}
```

## ECLP-0020: Capability Security

Status: Draft

Effects require capabilities. A function cannot perform filesystem access
merely because it knows the `FileSystem` type exists.

```evert
effect FileSystem {
    readText(path: Path) -> Text ! Throw<IoError>
    writeText(path: Path, text: Text) -> Unit ! Throw<IoError>
}
```

Capabilities may be passed explicitly:

```evert
fn loadConfig(fs: capability FileSystem, path: Path)
    -> Config ! Throw<ConfigError> {
    let text = fs.readText(path).mapErr(Io)?;
    parseConfig(text).mapErr(Parse)?
}
```

Or provided by handlers:

```evert
handle loadConfig(path) with SandboxFileSystem(root = "/app/config")
```

Rules:

```text
Capabilities are values.
Capabilities may be restricted, wrapped, logged or revoked.
The effect row states what kind of authority a computation requests.
Handlers supply or transform authority.
```

This gives Evert a security model that is not “please don’t import the spicy
package”.

## ECLP-0021: Unsafe, FFI and System Boundaries

Status: Draft

Unsafe code exists because systems programming exists. Evert fences it.

```evert
extern "C" {
    fn strlen(ptr: Ptr<UInt8>) -> Size ! Unsafe
}

fn cLength(text: Text) -> Size ! Unsafe {
    unsafe {
        withCString(text, ptr => strlen(ptr))
    }
}
```

Peglet form:

```peglet
@node
unsafe_expr =
    Unsafe ~ block
    => UnsafeExpr(block)
    recover nested LBrace RBrace until [EOF]
;

@node
extern_decl =
    Extern ~ abi:String LBrace items:extern_item* RBrace
    => ExternDecl { abi, items }
    recover nested LBrace RBrace until [EOF]
;

extern_item =
    Fn ~ name:Ident params:param_list ret:return_type? eff:effect_sig? Semi
    => ExternFn { name, params, ret, eff }
;
```

Unsafe powers:

```text
Raw pointer creation and dereference.
Pinned layout assumptions.
Explicit region parameters.
FFI calls.
Manual allocation.
Atomic memory ordering beyond safe defaults.
Unchecked casts.
```

Rules:

```text
unsafe is an effect.
unsafe blocks do not make surrounding code pure.
Unsafe APIs must state aliasing, lifetime and threading contracts.
Safe wrappers must discharge those contracts.
```

## ECLP-0022: Memory Model

Status: Draft

Evert’s safe memory model has four pillars:

```text
Immutable sharing is free.
Mutable sharing requires synchronization.
Linear resources have deterministic destruction.
Garbage collection and regions are implementation strategies, not source semantics.
```

The implementation may combine tracing GC, arenas, stack allocation, escape
analysis, reference counting, move-only resources and region allocation. The
source semantics only expose what matters:

```evert
using socket = Network.connect(addr)?;
let response = socket.request(req)?;
```

Concurrency memory rules:

```text
Plain immutable values may cross tasks if Send.
Mutable cells may not cross tasks.
Actor references may cross tasks if their protocol is Send.
Atomic<T> may cross tasks if T is AtomicValue.
Resources may cross tasks only through send transfer.
```

Atomics are explicit:

```evert
let counter = Atomic<Int>.new(0);
counter.fetchAdd(1, ordering = Relaxed);
```

Default safe concurrency never exposes memory orderings. If you are choosing
`AcquireRelease`, you are already in the engine room wearing goggles.

## ECLP-0023: Standard Prelude

Status: Draft

The prelude imports only stable, unsurprising names.

```text
Unit
Bool
Int
UInt
Float
Text
Char
Option
Result
Vector
Map
Set
Range
Iterator
Stream
Task
Send
Share
Drop
Eq
Ord
Hash
Show
```

Not in the prelude:

```text
FileSystem
Network
Clock
Random
Unsafe
Console
Global allocator controls
Cryptographic primitives
```

Rationale: authority should not arrive in scope wearing a party hat.

Prelude grammar does not need much syntax, but imports use ordinary module
rules:

```evert
use std.prelude.*;
use std.text.Text;
use std.collections.Vector;
```

## ECLP-0024: Metaprogramming Without Token Soup

Status: Wild Draft

Evert allows compile-time computation, derivation and syntax transforms, but
macros operate on typed syntax trees, not raw token confetti.

```evert
derive Json for User

macro sql(query: StaticText) -> Expr<DatabaseQuery> {
    parseSqlAtCompileTime(query)
}
```

Rules:

```text
Macros run at compile time.
Macro functions must be pure unless explicitly granted compiler capabilities.
Macros receive CST or AST nodes with spans.
Macros return syntax with hygiene.
Macros cannot inspect arbitrary local values unless those values are compile-time constants.
```

Peglet form:

```peglet
@node
macro_decl =
    Macro ~ name:Ident params:param_list ret:return_type body:block
    => MacroDecl { name, params, ret, body }
    recover nested LBrace RBrace until [EOF]
;

@node
derive_decl =
    Derive ~ trait_name:qualified_name For target:type_expr Semi
    => DeriveDecl { trait_name, target }
    recover until [Semi, EOF]
;
```

Macro example:

```evert
let query =
    sql("select id, name from users where id = ?")
```

If the SQL is malformed, the diagnostic points into the string literal. Tiny
parser lighthouse, now mounted inside a gemstone.

## ECLP-0025: Layout, Formatting and Recovery

Status: Draft

Evert accepts braces everywhere and layout where it improves readability.

Both forms are equivalent:

```evert
fn add(x: Int, y: Int) -> Int {
    x + y
}
```

```evert
fn add(x: Int, y: Int) -> Int =
    x + y
```

For block layout, the layout pass produces explicit tokens before parsing:

```peglet
layout_tokens =
      Indent
    / Dedent
    / Newline
;
```

Parser recovery is part of the grammar. The peglet guide recommends attaching
recovery where humans commonly make mistakes and testing invalid input
aggressively, which is precisely the posture Evert should take.

Example:

```peglet
@node
fn_decl =
    purity:purity? Fn ~ name:Ident params:type_params? args:param_list
    ret:return_type? eff:effect_sig? body:fn_body
    => FnDecl { purity, name, params, args, ret, eff, body }
    recover until [RBrace, Semi, EOF]
;
```

Preferred diagnostic style:

```text
error[E0312]: expected parameter name
  --> app.evt:12:18
   |
12 | fn greet(: Text) {
   |          ^ parameter name goes here
```

Not:

```text
expected token Ident while parsing generated_rule_74 after commitment
```

## ECLP-0026: Compiler Core Language

Status: Implementation Draft

The surface language lowers to a small, typed Core.

Core forms:

```text
Var
Let
Lambda
Apply
Constructor
Match
Record
Project
Update
Thunk
Force
Perform
Handle
Region
Mutate
Spawn
Await
Unsafe
```

Core types:

```text
T
T -> U ! E
Forall a. T
Exists a. T
Lazy<T>
Task<T, E>
Resource<T>
Region<r, T>
```

Surface syntax should never leak Core noise, but Core gives the compiler one
place to define semantics.

Lowering examples:

```evert
let lazy x = f(10)
```

becomes:

```text
let x = Thunk(lambda () -> f(10))
```

```evert
Console.say("hello")
```

becomes:

```text
perform Console.say("hello")
```

```evert
do Option {
    x <- a;
    y <- b(x);
    yield y;
}
```

becomes:

```text
Option.flatMap(a, lambda x ->
    Option.flatMap(b(x), lambda y ->
        Option.pure(y)))
```

The monad and the effect system may share continuation machinery after
lowering. Source users should not pay for that knowledge with forehead bruises.

## ECLP-0027: The Concurrency Ownership Compact

Status: Wild Draft

This is the heart of Evert’s “steal what works, fix what hurts” concurrency
model.

It steals:

```text
Rust’s ownership and Send/Sync insight.
Go’s cheap concurrent tasks and channels.
Swift’s structured concurrency and actors.
Mojo’s ambition to make systems concerns feel high level.
Haskell’s algebraic clarity.
```

It rejects:

```text
Rust’s lifetime typography in ordinary application code.
Go’s unstructured goroutine leaks.
Swift actor reentrancy by surprise.
Async function colouring as an architectural tax.
Global mutable state pretending to be convenient.
```

The compact:

```text
1. Every concurrent computation belongs to a nursery.
2. Every cross-task value must be Send.
3. Shared mutable state must be Actor, Atomic, Channel, or Unsafe.
4. Actor methods are non-reentrant unless explicitly marked.
5. Cancellation forms a tree.
6. Finalizers always run.
7. Detached tasks require system capability.
8. Blocking operations must declare Blocking or run on a blocking scheduler.
```

Example:

```evert
fn mirrorDownload(urls: Vector<Url>, output: Path)
    -> Unit ! { Async, Http, FileSystem, Throw<DownloadError> } {

    using file = FileSystem.create(output).mapErr(Io)?;

    let bytes =
        race {
            primary: Http.getBytes(urls[0]!)
            mirror:  Http.getBytes(urls[1]!)
        }.mapErr(Network)?;

    file.write(bytes).mapErr(Io)?;
}
```

A detached task looks deliberately noisy:

```evert
fn startDaemon(send cap: DetachedTaskCapability)
    -> DaemonId ! { Async, System } {

    cap.detach {
        runForever()
    }
}
```

That syntax should feel like opening a panel with a triangular screwdriver.

## ECLP-0028: Effects Meet Concurrency

Status: Wild Draft

Effects may be scoped to tasks.

```evert
nursery n {
    handle {
        n.spawn { Console.say("one") };
        n.spawn { Console.say("two") };
    } with BufferedConsole()
}
```

The handler decides whether child task effects are:

```text
inherited       child effects handled by parent handler
isolated        child receives a fresh handler instance
forbidden       child may not perform that effect
forwarded       child sends effect requests to parent task
```

Handler declaration:

```evert
handler BufferedConsole : Console {
    policy childEffects = forwarded

    op say(message: Text) resume {
        buffer.push(message);
        resume(())
    }

    op ask(prompt: Text) resume {
        resume(input.popFront())
    }
}
```

This avoids the hidden global logger problem and the “which task owns stdout?”
swamp.

## ECLP-0029: Editions and Compatibility

Status: Draft

Evert evolves through editions.

```text
edition 2026
edition 2029
edition 2032
```

Rules:

```text
An edition may change parsing defaults.
An edition may reserve new keywords.
An edition may improve inference if old code keeps compiling.
An edition may not silently change runtime meaning.
Packages declare their edition.
Modules from different editions may interoperate through typed interfaces.
```

Peglet hook:

```peglet
edition_decl =
    Edition ~ year:Int Semi
    => EditionDecl(year)
;
```

Language features have gates:

```evert
#!feature(nonreentrant_actors_v2)
#!edition(2026)
```

No extension confetti by default. Evert should not require a spellbook of
compiler flags before `hello world`.

## ECLP-0030: What Evert Refuses

Status: Accepted as Attitude

Evert refuses:

```text
Implicit null.
Ambient global IO.
Import-time execution.
Unstructured detached concurrency.
Effectful laziness.
Stringly typed reflection.
Orphan instances by default.
Partially initialized values in safe code.
Silent data races.
Macros that parse their own language badly.
Unsafe code without an Unsafe effect.
```

Evert allows:

```text
Low-level memory work.
Fast mutable algorithms.
Deterministic resources.
Actors.
Channels.
Laziness.
Monads.
Algebraic effects.
Typed metaprogramming.
FFI.
Compiler plugins eventually, with a muzzle and paperwork.
```

## A Tiny Unified Example

This pulls together the proposed model.

```evert
module app.main;

use std.console.Console;
use std.time.Clock;
use std.async.{nursery, race};
use std.result.Result;

data AppError =
    BadInput(Text)
  | Network(NetworkError)
  | Io(IoError)

effect UserStore {
    find(name: Text) -> Option<User> ! Throw<IoError>
    insert(user: User) -> Unit ! Throw<IoError>
}

record User {
    name: Text,
    age: Int
}

pure fn parseUser(nameText: Text, ageText: Text) -> Result<User, AppError> =
    do Result {
        name <- nonBlank(nameText).okOr(BadInput("missing name"));
        age  <- Int.parse(ageText).mapErr(_ => BadInput("bad age"));
        ensure age >= 18 else BadInput("too young");
        yield User { name, age };
    }

fn register() -> User
    ! { Console, Clock, UserStore, Throw<AppError> } {

    let nameText = Console.ask("Name: ");
    let ageText = Console.ask("Age: ");

    let user =
        parseUser(nameText, ageText).orThrow();

    match UserStore.find(user.name).mapErr(Io).orThrow() {
        Some(_) =>
            throw BadInput("user already exists"),

        None =>
            UserStore.insert(user).mapErr(Io).orThrow()
    }

    Console.say("Registered {user.name}");
    user
}
```

## The First Compiler Milestone Set

The minimal viable Evert should implement these in order:

```text
M0  Lexer, layout pass, CST parser with recovery.
M1  Names, modules, ADTs, records, pattern matching.
M2  Hindley-Milner-ish inference with public signature checking.
M3  Effect rows and pure fn enforcement.
M4  Core lowering and interpreter.
M5  Lazy thunks, pure-only validation.
M6  Result, Option, traits, do notation.
M7  Local mutate regions.
M8  Basic handlers for Throw and Console-like effects.
M9  Structured nursery, spawn, await, cancellation.
M10 Linear resources, using, Send checking.
M11 Actors and protocols.
M12 LLVM backend.
```

The crucial move is to build an interpreter before LLVM. Otherwise every
semantic bug will wear an optimiser moustache and deny everything.

## Closing Design Note

Evert’s north star is not “make Haskell easier” or “make Rust friendlier” or
“make Go safer”. Those are useful shadows, but not the object.

The object is a language where abstraction feels like choosing the right tool,
not joining a guild.

You can write:

```evert
pure fn area(shape: Shape) -> Float =
    match shape {
        Circle(r) => pi * r * r
        Rectangle(w, h) => w * h
    }
```

or:

```evert
fn serve() -> Unit ! { Async, Network, Throw<IoError> } {
    nursery clients {
        loop {
            using socket = Network.accept()?;
            clients.spawn {
                handleClient(socket)
            }
        }
    }
}
```

or:

```evert
pure fn fibs() -> Stream<Int> =
    let rec xs = Next(0, lazy Next(1, lazy zipWith(xs, xs.tail, (+))));
    xs
```

and the language should meet each programme where it stands.

Tiny squirrel flag planted. 🐿️
